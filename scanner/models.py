from django.db import models
from participants.models import Participant
from answer_keys.models import AnswerKey

class OMRSubmission(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('EVALUATED', 'Evaluated'),
        ('ERROR', 'Error'),
    ]

    participant = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name='omr_submission', blank=True, null=True)
    image = models.ImageField(upload_to='omr_sheets/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True, null=True)
    detected_answers = models.JSONField(blank=True, null=True)  # List of 50 detected values (0=unanswered, 1-4=A-D, 5=multi-marked)
    answer_key = models.ForeignKey(AnswerKey, on_delete=models.PROTECT, related_name='submissions', blank=True, null=True)

    def __str__(self):
        return f"Submission for {self.participant.roll_number} ({self.status})"
