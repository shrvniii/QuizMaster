import cv2
import numpy as np
import os
import shutil
import io
from unittest.mock import patch
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
        self.assertIn("Only ZIP and PDF files are supported", response.json()['error'])

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

    @patch('scanner.views.start_batch_processing')
    def test_batch_processing_pdf_execution(self, mock_start):
        import tempfile
        from reportlab.pdfgen import canvas
        
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
                    
        # Write mock image to temporary file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
            cv2.imwrite(tmp_img.name, img)
            tmp_img_name = tmp_img.name
            
        # Draw image onto ReportLab PDF canvas
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=(1000, 1200))
        c.drawImage(tmp_img_name, 0, 0, width=1000, height=1200)
        c.showPage()
        c.save()
        
        # Cleanup temporary image file
        try:
            os.remove(tmp_img_name)
        except Exception:
            pass
            
        pdf_buffer.seek(0)
        
        # Post request with PDF using SimpleUploadedFile to provide name and content-type
        from django.core.files.uploadedfile import SimpleUploadedFile
        pdf_file = SimpleUploadedFile("batch.pdf", pdf_buffer.getvalue(), content_type="application/pdf")
        response = self.client.post(reverse('api_bulk_upload'), {'file': pdf_file})
        self.assertEqual(response.status_code, 200)
        batch_id = response.json()['batchId']
        self.assertIsNotNone(batch_id)
        
        # Wait/retrieve progress (synchronous test check)
        from django.conf import settings
        from .batch_processor import process_batch_async
        
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_batches', batch_id)
        extract_path = os.path.join(temp_dir, 'extracted')
        
        # Verify Batch record was created in views and exists
        batch = BatchProcess.objects.get(batch_id=batch_id)
        self.assertEqual(batch.status, 'queued')
        
        # Since the background process was triggered in view but thread is async,
        # we can run the processing step synchronously for test verification
        valid_files = sorted(os.listdir(extract_path))
        self.assertEqual(len(valid_files), 1)
        self.assertEqual(valid_files[0], 'page_001.png')
        
        process_batch_async(batch_id, extract_path, valid_files)
        
        # Refresh and verify results
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed')
        self.assertEqual(batch.total, 1)
        self.assertEqual(batch.success, 1)
        self.assertEqual(batch.failed, 0)
        self.assertEqual(batch.percentage, 100)
        
        # Cleanup files on disk
        for sub in OMRSubmission.objects.all():
            if sub.image and os.path.exists(sub.image.path):
                os.remove(sub.image.path)
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, 'temp_batches', batch_id), ignore_errors=True)
        print("Bulk OMR PDF pipeline unit test passed successfully!")


class ParticipantValidationTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test Academy", code="02")

    def test_valid_junior_roll_number(self):
        p = Participant(
            roll_number="02005",
            full_name="Junior Valid",
            school=self.school,
            group="JUNIOR",
            paper_set="SET_A"
        )
        # Should not raise any ValidationError
        p.full_clean()
        p.save()
        self.assertTrue(Participant.objects.filter(roll_number="02005").exists())

    def test_invalid_junior_roll_number(self):
        from django.core.exceptions import ValidationError
        p = Participant(
            roll_number="02505",  # 505 is in senior range
            full_name="Junior Invalid",
            school=self.school,
            group="JUNIOR",
            paper_set="SET_A"
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_valid_senior_roll_number(self):
        p = Participant(
            roll_number="02505",
            full_name="Senior Valid",
            school=self.school,
            group="SENIOR",
            paper_set="SET_B"
        )
        # Should not raise any ValidationError
        p.full_clean()
        p.save()
        self.assertTrue(Participant.objects.filter(roll_number="02505").exists())

    def test_invalid_senior_roll_number(self):
        from django.core.exceptions import ValidationError
        p = Participant(
            roll_number="02005",  # 005 is in junior range
            full_name="Senior Invalid",
            school=self.school,
            group="SENIOR",
            paper_set="SET_B"
        )
        with self.assertRaises(ValidationError):
            p.full_clean()



