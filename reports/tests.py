from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from schools.models import School
from participants.models import Participant
from scanner.models import OMRSubmission
from results.models import Result

class CSVDownloadTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='password123')
        self.school = School.objects.create(name="Test School", code="01")
        self.participant = Participant.objects.create(
            roll_number="01001",
            school=self.school,
            group="JUNIOR",
            paper_set="SET_A"
        )
        self.submission = OMRSubmission.objects.create(
            participant=self.participant,
            status='EVALUATED'
        )
        self.result = Result.objects.create(
            submission=self.submission,
            participant=self.participant,
            score=45,
            percentage=90.0,
            unanswered_count=2,
            multi_marked_count=1,
            question_breakdown=[]
        )
        
    def test_csv_download(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:csv_download'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content
        self.assertIn(b"01001", content)
        self.assertIn(b"Test School", content)


class PregeneratedOMRTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_omr', password='password123')
        
    def test_junior_omr_download(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:download_pregenerated_omr', kwargs={'school_code': '05', 'group': 'junior'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="School_05_junior_OMR_Pack.pdf"', response['Content-Disposition'])

    def test_senior_omr_download(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:download_pregenerated_omr', kwargs={'school_code': '40', 'group': 'senior'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="School_40_senior_OMR_Pack.pdf"', response['Content-Disposition'])

    def test_invalid_school_code(self):
        self.client.force_login(self.user)
        # Suffix/code too long
        response1 = self.client.get(reverse('reports:download_pregenerated_omr', kwargs={'school_code': '123', 'group': 'junior'}))
        self.assertEqual(response1.status_code, 404)
        # Out of bounds code
        response2 = self.client.get(reverse('reports:download_pregenerated_omr', kwargs={'school_code': '51', 'group': 'junior'}))
        self.assertEqual(response2.status_code, 404)

    def test_invalid_group(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:download_pregenerated_omr', kwargs={'school_code': '01', 'group': 'invalid'}))
        self.assertEqual(response.status_code, 404)
