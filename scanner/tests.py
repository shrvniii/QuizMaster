import cv2
import numpy as np
import os
from django.test import TestCase
from django.core.files.base import ContentFile
from schools.models import School
from participants.models import Participant
from answer_keys.models import AnswerKey
from scanner.models import OMRSubmission
from results.models import Result
from scanner.evaluator import evaluate_and_grade_submission, get_row_y_coordinate

class OMRPipelineTestCase(TestCase):
    def setUp(self):
        # Create school and participant
        self.school = School.objects.create(name="Test Academy", code="02")
        self.participant = Participant.objects.create(
            roll_number="02001",
            full_name="Bob Jones",
            school=self.school,
            group="JUNIOR",
            paper_set="SET_A"
        )
        
        # Create Answer Key: Q1=A(1), Q2=B(2), Q3=C(3), Q4=D(4), and Q5-Q50 = A(1)
        self.answers = [1] * 50
        self.answers[0] = 1 # Q1 = A
        self.answers[1] = 2 # Q2 = B
        self.answers[2] = 3 # Q3 = C
        self.answers[3] = 4 # Q4 = D
        
        self.answer_key = AnswerKey.objects.create(
            group="JUNIOR",
            paper_set="SET_A",
            answers=self.answers
        )

    def test_omr_grading_pipeline(self):
        # Create a mock OMR sheet image in memory
        # Dimensions: 1000 x 1200 pixels
        img = np.ones((1200, 1000, 3), dtype="uint8") * 255
        
        # Draw 4 solid black square anchors (size 16x16)
        # We place them at (50, 50), (950, 50), (50, 1150), (950, 1150)
        cv2.rectangle(img, (42, 42), (58, 58), (0, 0, 0), -1)   # TL
        cv2.rectangle(img, (942, 42), (958, 58), (0, 0, 0), -1) # TR
        cv2.rectangle(img, (42, 1142), (58, 1158), (0, 0, 0), -1) # BL
        cv2.rectangle(img, (942, 1142), (958, 1158), (0, 0, 0), -1) # BR
        
        # Warped coordinates:
        # col1_x = 225 pt in PDF -> 359, 402, 445, 487
        col1_x_centers = [359, 402, 445, 487]
        # col2_x = 410 pt in PDF -> 718, 761, 804, 847
        col2_x_centers = [718, 761, 804, 847]
        
        row_y_centers = [int((660 - get_row_y_coordinate(r)) * 2) for r in range(25)]
        
        # Define what the student marks:
        # Q1: Marks A (Correct: A) -> Score+1
        # Q2: Marks B (Correct: B) -> Score+1
        # Q3: Marks D (Correct: C) -> Incorrect
        # Q4: Marks C (Correct: D) -> Incorrect
        # Q5: Blank (Correct: A) -> Unanswered
        # Q6: Marks A & B (Correct: A) -> Multi-marked
        # Q7 - Q50: Marks A (Correct: A) -> Score+44
        # Total expected score = 1 + 1 + 0 + 0 + 0 + 0 + 44 = 46/50
        # Expected unanswered = 1
        # Expected multi-marked = 1
        
        student_marks = {}
        student_marks[0] = [1]    # Q1: A
        student_marks[1] = [2]    # Q2: B
        student_marks[2] = [4]    # Q3: D (Wrong)
        student_marks[3] = [3]    # Q4: C (Wrong)
        student_marks[4] = []     # Q5: Blank
        student_marks[5] = [1, 2] # Q6: A & B (Multi)
        for q in range(6, 50):
            student_marks[q] = [1] # Q7-Q50: A (Correct)
 
        # Draw Roll No bubbles for "02001" on the mock sheet
        # Digits: [0, 2, 0, 0, 1]
        roll_digits = [0, 2, 0, 0, 1]
        roll_x_centers = [76, 111, 146, 181, 216]
        
        for col_idx, digit in enumerate(roll_digits):
            cx = roll_x_centers[col_idx]
            ox = int(50 + cx * 0.9)
            
            for row_idx in range(10):
                cy = 260 + row_idx * 36
                oy = int(50 + cy * (1100.0 / 1200.0))
                
                if row_idx == digit:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), -1) # Filled
                else:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), 1)  # Empty
        
        # Draw the question bubbles on our mock sheet
        for q in range(50):
            col = 0 if q < 25 else 1
            row_idx = q if q < 25 else q - 25
            
            x_centers = col1_x_centers if col == 0 else col2_x_centers
            wy = row_y_centers[row_idx]
            
            # Map Y to original image space
            oy = int(50 + wy * (1100.0 / 1200.0))
            
            marks = student_marks[q]
            
            for bubble_idx in range(1, 5):
                wx = x_centers[bubble_idx - 1]
                # Map X to original image space
                ox = int(50 + wx * 0.9)
                
                if bubble_idx in marks:
                    # Draw filled bubble (solid black circle)
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), -1)
                else:
                    # Draw empty bubble (circle outline)
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), 1)
                    
        # Encode image to bytes
        _, img_encoded = cv2.imencode('.png', img)
        img_bytes = img_encoded.tobytes()
        
        # Save OMR Submission without participant/answer_key to test auto-detection
        submission = OMRSubmission.objects.create(
            status='PENDING'
        )
        # Write image using Django File API
        submission.image.save('test_sheet.png', ContentFile(img_bytes))
        submission.save()
        
        # Run evaluation pipeline
        success, msg = evaluate_and_grade_submission(submission.pk)
        
        # Assertions
        self.assertTrue(success, f"Grading failed: {msg}")
        
        # Reload submission and result
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'EVALUATED')
        
        # Verify auto-detection linked the correct participant and answer key
        self.assertEqual(submission.participant, self.participant)
        self.assertEqual(submission.answer_key, self.answer_key)
        
        result = submission.result
        self.assertEqual(result.score, 46)
        self.assertEqual(result.unanswered_count, 1)
        self.assertEqual(result.multi_marked_count, 1)
        self.assertEqual(result.percentage, 92.0)
        
        # Verify question breakdown details
        breakdown = result.question_breakdown
        self.assertEqual(breakdown[0]['status'], 'correct')      # Q1
        self.assertEqual(breakdown[1]['status'], 'correct')      # Q2
        self.assertEqual(breakdown[2]['status'], 'incorrect')    # Q3
        self.assertEqual(breakdown[3]['status'], 'incorrect')    # Q4
        self.assertEqual(breakdown[4]['status'], 'unanswered')   # Q5
        self.assertEqual(breakdown[5]['status'], 'multi-marked')  # Q6
        self.assertEqual(breakdown[6]['status'], 'correct')      # Q7
        
        # Cleanup file on disk
        if os.path.exists(submission.image.path):
            os.remove(submission.image.path)
            
        print("OMR pipeline unit test passed successfully with new layout!")

from django.contrib.auth.models import User
from django.urls import reverse
import io
import zipfile
from .models import BatchProcess
from .batch_processor import process_batch_async, safe_extract_zip

class BulkOMRUploadTestCase(TestCase):
    def setUp(self):
        # Create school and participant
        self.school = School.objects.create(name="Test Academy 2", code="03")
        self.participant = Participant.objects.create(
            roll_number="03001",
            full_name="Alice Smith",
            school=self.school,
            group="JUNIOR",
            paper_set="SET_A"
        )
        
        # Create Answer Key
        self.answers = [1] * 50
        self.answer_key = AnswerKey.objects.create(
            group="JUNIOR",
            paper_set="SET_A",
            answers=self.answers
        )
        
        # Create user for login
        self.user = User.objects.create_user(username='tester', password='password123')
        self.client.force_login(self.user)

    def test_api_bulk_upload_validation(self):
        # Post request with no file
        response = self.client.post(reverse('api_bulk_upload'), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("No file uploaded", response.json()['error'])
        
        # Post request with wrong extension
        bad_file = io.BytesIO(b"dummy text content")
        bad_file.name = "test.txt"
        response = self.client.post(reverse('api_bulk_upload'), {'file': bad_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only ZIP files are supported", response.json()['error'])

    def test_batch_processing_execution(self):
        # Construct a mock OMR sheet image
        img = np.ones((1200, 1000, 3), dtype="uint8") * 255
        
        # Draw anchors
        cv2.rectangle(img, (42, 42), (58, 58), (0, 0, 0), -1)   # TL
        cv2.rectangle(img, (942, 42), (958, 58), (0, 0, 0), -1) # TR
        cv2.rectangle(img, (42, 1142), (58, 1158), (0, 0, 0), -1) # BL
        cv2.rectangle(img, (942, 1142), (958, 1158), (0, 0, 0), -1) # BR
        
        # Draw Roll No bubbles for "03001"
        roll_digits = [0, 3, 0, 0, 1]
        roll_x_centers = [76, 111, 146, 181, 216]
        
        for col_idx, digit in enumerate(roll_digits):
            cx = roll_x_centers[col_idx]
            ox = int(50 + cx * 0.9)
            
            for row_idx in range(10):
                cy = 260 + row_idx * 36
                oy = int(50 + cy * (1100.0 / 1200.0))
                
                if row_idx == digit:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), -1) # Filled
                else:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), 1)  # Empty
        
        # Draw question bubbles (all set to A/1)
        col1_x_centers = [359, 402, 445, 487]
        col2_x_centers = [718, 761, 804, 847]
        row_y_centers = [int((660 - get_row_y_coordinate(r)) * 2) for r in range(25)]
        
        for q in range(50):
            col = 0 if q < 25 else 1
            row_idx = q if q < 25 else q - 25
            
            x_centers = col1_x_centers if col == 0 else col2_x_centers
            wy = row_y_centers[row_idx]
            oy = int(50 + wy * (1100.0 / 1200.0))
            
            # Bubble index 1 (which is A) is filled
            for bubble_idx in range(1, 5):
                wx = x_centers[bubble_idx - 1]
                ox = int(50 + wx * 0.9)
                if bubble_idx == 1:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), -1)
                else:
                    cv2.circle(img, (ox, oy), 8, (0, 0, 0), 1)
                    
        # Encode image to bytes
        _, img_encoded = cv2.imencode('.png', img)
        img_bytes = img_encoded.tobytes()
        
        # Create in-memory ZIP containing the image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr('sheet1.png', img_bytes)
            zf.writestr('info.txt', b'random ignored text file')
            
        zip_buffer.seek(0)
        
        # Create BatchProcess db entry
        batch_id = "testbatch999"
        batch = BatchProcess.objects.create(
            batch_id=batch_id,
            status='queued',
            total=1,
            processed=0,
            success=0,
            failed=0,
            percentage=0
        )
        
        # Set up extract path
        from django.conf import settings
        extract_dir = os.path.join(settings.MEDIA_ROOT, 'temp_batches_test', batch_id)
        os.makedirs(extract_dir, exist_ok=True)
        
        zip_file_path = os.path.join(extract_dir, 'batch.zip')
        with open(zip_file_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
            
        # Extract and process
        safe_extract_zip(zip_file_path, extract_dir)
        os.remove(zip_file_path)
        
        # Process synchronously
        valid_files = ['sheet1.png']
        process_batch_async(batch_id, extract_dir, valid_files)
        
        # Verify Batch results
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed')
        self.assertEqual(batch.total, 1)
        self.assertEqual(batch.success, 1)
        self.assertEqual(batch.failed, 0)
        self.assertEqual(batch.percentage, 100)
        
        # Clean up files on disk
        for sub in OMRSubmission.objects.all():
            if sub.image and os.path.exists(sub.image.path):
                os.remove(sub.image.path)
        
        import shutil
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, 'temp_batches_test'), ignore_errors=True)
                
        print("Bulk OMR pipeline unit test passed successfully!")

