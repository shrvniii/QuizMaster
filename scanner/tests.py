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
