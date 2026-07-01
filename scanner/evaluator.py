import cv2
import numpy as np
from django.db import transaction
from django.utils import timezone
from .models import OMRSubmission
from results.models import Result
from answer_keys.models import AnswerKey

def detect_anchors(img_gray):
    # Apply Gaussian blur and adaptive thresholding to get binary image
    blurred = cv2.GaussianBlur(img_gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    img_h, img_w = img_gray.shape
    min_area = (img_w * img_h) * 0.00005  # Loosened min area (0.005%)
    max_area = (img_w * img_h) * 0.02     # Loosened max area (2%)
    
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if min_area < area < max_area:
            # Check aspect ratio
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = float(w) / h
            
            # Loosened aspect ratio (0.5 to 2.0) to handle phone photo perspective distortion
            if 0.5 <= aspect_ratio <= 2.0:
                # Check solidity (squareness)
                rect_area = w * h
                solidity = float(area) / rect_area if rect_area > 0 else 0
                
                # Loosened solidity threshold (0.2) to support L-shaped brackets and degraded print quality
                if solidity > 0.2:
                    # Store center point
                    cx = x + w / 2
                    cy = y + h / 2
                    candidates.append((cx, cy))
                    
    if len(candidates) < 4:
        raise ValueError(f"Could not find all 4 corner registration marks. Found {len(candidates)} candidates.")
        
    # If we have more than 4 candidates, filter to keep the ones closest to the corners of the image
    corners = [
        (0, 0),          # Top-Left
        (img_w, 0),      # Top-Right
        (0, img_h),      # Bottom-Left
        (img_w, img_h)   # Bottom-Right
    ]
    
    selected_anchors = []
    for corner in corners:
        # Find candidate closest to this corner
        best_candidate = min(candidates, key=lambda pt: (pt[0] - corner[0])**2 + (pt[1] - corner[1])**2)
        selected_anchors.append(best_candidate)
        
    # Order of selected_anchors is: TL, TR, BL, BR
    return np.array(selected_anchors, dtype="float32")

def warp_image(img, anchors):
    # Standard warped size
    width, height = 1000, 1200
    
    # Source points (anchors)
    # Order: Top-Left, Top-Right, Bottom-Left, Bottom-Right
    sorted_by_y = anchors[np.argsort(anchors[:, 1])]
    
    # Top points are the two with smaller y
    top = sorted_by_y[:2]
    tl = top[np.argmin(top[:, 0])]
    tr = top[np.argmax(top[:, 0])]
    
    # Bottom points are the two with larger y
    bottom = sorted_by_y[2:]
    bl = bottom[np.argmin(bottom[:, 0])]
    br = bottom[np.argmax(bottom[:, 0])]
    
    src = np.array([tl, tr, bl, br], dtype="float32")
    
    # Destination points
    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [0, height - 1],
        [width - 1, height - 1]
    ], dtype="float32")
    
    # Compute perspective transform matrix and warp
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (width, height))
    
    return warped

def get_row_y_coordinate(r):
    """
    Returns the Y coordinate (in PDF points) for a given row index r (0 to 24).
    Matches the formula in omr_generator.py.
    """
    block_idx = r // 5
    row_in_block = r % 5
    return 590 - (block_idx * 105) - (row_in_block * 18)

def evaluate_sheet(warped_gray):
    # Restored to theoretical PDF coordinates mapping in 1000x1200 warped space
    col1_x_centers = [359, 402, 445, 487]
    col2_x_centers = [718, 761, 804, 847]
    row_y_centers = [int((660 - get_row_y_coordinate(r)) * 2) for r in range(25)]
    
    bubble_r = 10  # Radius in pixels
    detected_answers = []
    
    # Apply Otsu's thresholding to get a clean binary image
    # Invert so bubbles are white (255) and paper is black (0)
    _, thresh = cv2.threshold(warped_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    def check_question(x_centers, y):
        bubble_stats = []
        
        for idx, cx in enumerate(x_centers):
            # Crop bubble region
            x1 = int(cx - bubble_r)
            y1 = int(y - bubble_r)
            x2 = int(cx + bubble_r)
            y2 = int(y + bubble_r)
            
            bubble_crop = thresh[y1:y2, x1:x2]
            
            # Create circular mask
            mask = np.zeros(bubble_crop.shape, dtype="uint8")
            cv2.circle(mask, (bubble_r, bubble_r), bubble_r - 2, 255, -1)
            
            # Calculate percentage of filled pixels in the mask area
            masked_crop = cv2.bitwise_and(bubble_crop, bubble_crop, mask=mask)
            total_pixels = cv2.countNonZero(mask)
            if total_pixels == 0:
                fill_ratio = 0
            else:
                filled_pixels = cv2.countNonZero(masked_crop)
                fill_ratio = float(filled_pixels) / total_pixels
            bubble_stats.append(fill_ratio)
            
        # Determine which bubbles are filled
        # Threshold adjusted to 0.60 to distinguish empty bubbles with letters/borders (0.3-0.45) from filled bubbles (~0.85-1.0)
        fill_threshold = 0.60
        filled_indices = [i + 1 for i, ratio in enumerate(bubble_stats) if ratio > fill_threshold]
        
        if len(filled_indices) == 1:
            return filled_indices[0]  # Exactly one bubble filled (1 = A, 2 = B, 3 = C, 4 = D)
        elif len(filled_indices) == 0:
            return 0  # Unanswered
        else:
            return 5  # Multi-marked (double-marked)
            
    # Process Q1 - Q25
    for r in range(25):
        y = row_y_centers[r]
        ans = check_question(col1_x_centers, y)
        detected_answers.append(ans)
        
    # Process Q26 - Q50
    for r in range(25):
        y = row_y_centers[r]
        ans = check_question(col2_x_centers, y)
        detected_answers.append(ans)
        
    return detected_answers

def detect_roll_number(thresh):
    """
    Scans the 5-column by 10-row roll number bubble grid on the warped OMR sheet.
    Returns a 5-digit string, using '?' for columns where detection was unclear.
    """
    # Restored to theoretical PDF coordinates mapping
    roll_x_centers = [76, 111, 146, 181, 216]
    roll_y_centers = [260 + r * 36 for r in range(10)]
    bubble_r = 10
    
    roll_digits = []
    fill_threshold = 0.60
    
    for col_idx in range(5):
        cx = roll_x_centers[col_idx]
        bubble_stats = []
        
        for row_idx in range(10):
            cy = roll_y_centers[row_idx]
            
            # Crop bubble region
            x1 = int(cx - bubble_r)
            y1 = int(cy - bubble_r)
            x2 = int(cx + bubble_r)
            y2 = int(cy + bubble_r)
            
            bubble_crop = thresh[y1:y2, x1:x2]
            
            # Create circular mask
            mask = np.zeros(bubble_crop.shape, dtype="uint8")
            cv2.circle(mask, (bubble_r, bubble_r), bubble_r - 2, 255, -1)
            
            # Calculate fill ratio
            masked_crop = cv2.bitwise_and(bubble_crop, bubble_crop, mask=mask)
            total_pixels = cv2.countNonZero(mask)
            if total_pixels == 0:
                fill_ratio = 0
            else:
                filled_pixels = cv2.countNonZero(masked_crop)
                fill_ratio = float(filled_pixels) / total_pixels
            
            bubble_stats.append(fill_ratio)
            
        # Find the bubble with the highest fill ratio in this column
        max_ratio = max(bubble_stats)
        max_idx = bubble_stats.index(max_ratio)
        
        # Using increased threshold (0.60) to avoid false positives on border lines
        if max_ratio > fill_threshold:
            roll_digits.append(str(max_idx))
        else:
            roll_digits.append("?")
            
    return "".join(roll_digits)

def detect_exam_set(thresh):
    """
    Detects which Exam Set bubble is filled (Set A or Set B).
    Returns 'SET_A', 'SET_B', or None if unclear.
    """
    # Restored to theoretical PDF coordinates mapping
    set_x_centers = [64, 107]
    cy = 104
    bubble_r = 10
    fill_threshold = 0.60
    
    bubble_stats = []
    for cx in set_x_centers:
        x1 = int(cx - bubble_r)
        y1 = int(cy - bubble_r)
        x2 = int(cx + bubble_r)
        y2 = int(cy + bubble_r)
        
        bubble_crop = thresh[y1:y2, x1:x2]
        mask = np.zeros(bubble_crop.shape, dtype="uint8")
        cv2.circle(mask, (bubble_r, bubble_r), bubble_r - 2, 255, -1)
        
        masked_crop = cv2.bitwise_and(bubble_crop, bubble_crop, mask=mask)
        total_pixels = cv2.countNonZero(mask)
        if total_pixels == 0:
            fill_ratio = 0
        else:
            filled_pixels = cv2.countNonZero(masked_crop)
            fill_ratio = float(filled_pixels) / total_pixels
        bubble_stats.append(fill_ratio)
        
    # Determine set based on which bubble is filled (> 60%)
    if bubble_stats[0] > fill_threshold and bubble_stats[1] <= fill_threshold:
        return 'SET_A'
    elif bubble_stats[1] > fill_threshold and bubble_stats[0] <= fill_threshold:
        return 'SET_B'
    else:
        return None

def evaluate_and_grade_submission(submission_id):
    """
    Main pipeline to grade a submission within a database transaction.
    """
    from participants.models import Participant
    
    with transaction.atomic():
        submission = OMRSubmission.objects.select_for_update().get(pk=submission_id)
        
        try:
            # Load image using OpenCV
            image_path = submission.image.path
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError("Could not load image file.")
                
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Step 1: Detect anchors
            anchors = detect_anchors(gray)
            
            # Step 2: Warp perspective
            warped = warp_image(gray, anchors)
            
            # Step 3: Threshold warped image to get a binary version for bubble evaluation
            _, thresh = cv2.threshold(warped, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Step 4: Auto-detect roll number if participant is not set
            if not submission.participant:
                detected_roll = detect_roll_number(thresh)
                
                # Check if it was only partially bubbled (contains '?')
                if "?" in detected_roll:
                    # Try to resolve it if there is a unique candidate matching the filled prefix
                    prefix = detected_roll.replace("?", "")
                    if len(prefix) >= 2:  # Must have at least the 2-digit school code prefix
                        matches = Participant.objects.filter(roll_number__startswith=prefix)
                        
                        # Exclude candidates who already have an OMR submission
                        available_matches = []
                        for p in matches:
                            if not OMRSubmission.objects.filter(participant=p).exclude(pk=submission.pk).exists():
                                available_matches.append(p)
                                
                        if len(available_matches) == 1:
                            participant = available_matches[0]
                            # Soft fallback log
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.info(f"OMR Roll No partially bubbled as '{detected_roll}'. Unique match resolved to: {participant.full_name} ({participant.roll_number})")
                        else:
                            raise ValueError(
                                f"Could not clearly read the roll number from the sheet. Detected '{detected_roll}'. "
                                f"Found {len(available_matches)} potential candidate matches in the database."
                            )
                    else:
                        raise ValueError(f"Could not clearly read the roll number from the sheet. Detected: {detected_roll}")
                else:
                    try:
                        participant = Participant.objects.get(roll_number=detected_roll)
                    except Participant.DoesNotExist:
                        raise ValueError(f"Detected roll number '{detected_roll}', but no such participant is registered.")
                    
                    # Check if this participant already has a submission
                    if OMRSubmission.objects.filter(participant=participant).exclude(pk=submission.pk).exists():
                        raise ValueError(f"Participant {participant.full_name} ({detected_roll}) already has an OMR submission.")
                
                submission.participant = participant
            
            # Step 5: Auto-resolve answer key if not set
            if not submission.answer_key:
                try:
                    answer_key = AnswerKey.objects.get(
                        group=submission.participant.group,
                        paper_set=submission.participant.paper_set
                    )
                    submission.answer_key = answer_key
                except AnswerKey.DoesNotExist:
                    raise ValueError(
                        f"The Answer Key for '{submission.participant.get_group_display()} - "
                        f"{submission.participant.get_paper_set_display()}' has not been configured yet."
                    )
            
            # Step 6: Evaluate question bubbles
            detected_answers = evaluate_sheet(warped)
            
            # Step 7: Compare against answer key
            answer_key = submission.answer_key
            correct_answers = answer_key.answers
            
            score = 0
            unanswered_count = 0
            multi_marked_count = 0
            question_breakdown = []
            
            option_map = {1: 'A', 2: 'B', 3: 'C', 4: 'D', 0: '—', 5: 'MULTI'}
            
            for i in range(50):
                detected = detected_answers[i]
                correct = correct_answers[i]
                
                status = "incorrect"
                if detected == correct:
                    score += 1
                    status = "correct"
                elif detected == 0:
                    unanswered_count += 1
                    status = "unanswered"
                elif detected == 5:
                    multi_marked_count += 1
                    status = "multi-marked"
                    
                question_breakdown.append({
                    "q_no": i + 1,
                    "detected": option_map.get(detected, '—'),
                    "correct": option_map.get(correct, '—'),
                    "status": status
                })
                
            # Calculate percentage
            percentage = (score / 50) * 100
            
            # Save OMRSubmission details
            submission.detected_answers = detected_answers
            submission.status = 'EVALUATED'
            submission.error_message = None
            submission.save()
            
            # Save or update Result
            Result.objects.update_or_create(
                submission=submission,
                defaults={
                    'participant': submission.participant,
                    'score': score,
                    'percentage': percentage,
                    'unanswered_count': unanswered_count,
                    'multi_marked_count': multi_marked_count,
                    'question_breakdown': question_breakdown
                }
            )
            
            # Lock the answer key so it cannot be edited
            if not answer_key.is_locked:
                answer_key.is_locked = True
                answer_key.save()
                
            return True, "Evaluation completed successfully."
            
        except Exception as e:
            # Mark submission as ERROR
            submission.status = 'ERROR'
            submission.error_message = str(e)
            submission.save()
            
            # Delete any existing Result if it failed this time
            Result.objects.filter(submission=submission).delete()
            
            return False, f"Evaluation failed: {str(e)}"
