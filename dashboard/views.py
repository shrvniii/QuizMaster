from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Avg, Max, Min
from django.contrib import messages
import os
from django.conf import settings
from schools.models import School
from participants.models import Participant
from scanner.models import OMRSubmission
from results.models import Result
from answer_keys.models import AnswerKey

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        evaluator_name = request.session.get('evaluator_name')
        if not evaluator_name:
            return render(request, 'scanner/enter_evaluator.html', {'next_url': request.path})
            
        total_schools = School.objects.count()
        total_participants = Participant.objects.count()
        
        junior_count = Participant.objects.filter(group='JUNIOR').count()
        senior_count = Participant.objects.filter(group='SENIOR').count()
        
        evaluated_count = OMRSubmission.objects.filter(status='EVALUATED').count()
        error_count = OMRSubmission.objects.filter(status='ERROR').count()
        
        # 1. Total Generated Sheets (400 per school)
        total_generated_sheets = total_schools * 400
        
        # 2. Remaining Count
        remaining_count = max(0, total_generated_sheets - evaluated_count)
        
        # 3. Duplicate Count (Submissions that failed due to duplicate check)
        duplicate_count = OMRSubmission.objects.filter(
            status='ERROR', 
            error_message__startswith='DUPLICATE_SCAN'
        ).count()
        
        # 4. Review-Required Count (Submissions that failed due to validation/alignment/etc.)
        review_required_count = OMRSubmission.objects.filter(status='ERROR').exclude(
            error_message__startswith='DUPLICATE_SCAN'
        ).count()
        
        progress_pct = 0
        if total_generated_sheets > 0:
            progress_pct = int((evaluated_count / total_generated_sheets) * 100)
            
        # Score aggregates
        avg_score = Result.objects.aggregate(avg=Avg('score'))['avg'] or 0
        high_score = Result.objects.aggregate(max=Max('score'))['max'] or 0
        low_score = Result.objects.aggregate(min=Min('score'))['min'] or 0
        
        # 5. Average Confidence Score
        avg_confidence = Result.objects.aggregate(avg=Avg('confidence_score'))['avg'] or 0
        
        # Recent uploads
        recent_uploads = OMRSubmission.objects.select_related('participant', 'participant__school').order_by('-uploaded_at')[:10]
        
        # Check Answer Keys
        keys_configured = AnswerKey.objects.count()
        keys_ready = (keys_configured == 4)
        
        # 6. School-wise progress stats
        schools = School.objects.all().order_by('code')
        school_list = []
        for s in schools:
            scanned = OMRSubmission.objects.filter(
                participant__school=s,
                status='EVALUATED'
            ).count()
            total_sheets = 400
            remaining = max(0, total_sheets - scanned)
            progress = int((scanned / total_sheets) * 100) if total_sheets > 0 else 0
            
            school_list.append({
                'school': s,
                'scanned': scanned,
                'remaining': remaining,
                'progress': progress
            })
            
        context = {
            'total_schools': total_schools,
            'total_participants': total_participants,
            'junior_count': junior_count,
            'senior_count': senior_count,
            'evaluated_count': evaluated_count,
            'total_generated_sheets': total_generated_sheets,
            'remaining_count': remaining_count,
            'duplicate_count': duplicate_count,
            'review_required_count': review_required_count,
            'progress_pct': progress_pct,
            'avg_score': round(avg_score, 1),
            'high_score': high_score,
            'low_score': low_score,
            'avg_confidence': round(avg_confidence, 1),
            'recent_uploads': recent_uploads,
            'keys_configured': keys_configured,
            'keys_ready': keys_ready,
            'school_list': school_list,
        }
        
        return render(request, 'dashboard/home.html', context)

class SettingsView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'dashboard/settings.html')

class ResetDataView(LoginRequiredMixin, View):
    def post(self, request):
        # Verify that the user confirmed by typing "RESET" in the form
        confirm_text = request.POST.get('confirm_text', '').strip()
        if confirm_text != "RESET":
            messages.error(request, "Data reset cancelled. You must type 'RESET' to confirm.")
            return redirect('dashboard:settings')

        try:
            with transaction.atomic():
                # 1. Delete OMR image files from disk
                submissions = OMRSubmission.objects.all()
                for sub in submissions:
                    if sub.image and os.path.exists(sub.image.path):
                        try:
                            os.remove(sub.image.path)
                        except OSError:
                            pass
                
                # 2. Delete database records (CASCADE will handle Results and Submissions)
                Result.objects.all().delete()
                OMRSubmission.objects.all().delete()
                Participant.objects.all().delete()
                School.objects.all().delete()
                AnswerKey.objects.all().delete()
                
            messages.success(request, "System database has been successfully reset! All schools, participants, answer keys, and results have been deleted.")
        except Exception as e:
            messages.error(request, f"Error resetting database: {str(e)}")
            
        return redirect('dashboard:home')

class RestoreSchoolsView(LoginRequiredMixin, View):
    def post(self, request):
        schools_data = [
            ('01', 'New Horizons Public School'),
            ('02', 'Mansoravar High School, Kamothe'),
            ('03', 'ST Agrasen High School, Kamothe'),
            ('04', 'CKT High School, English Medium'),
            ('05', 'Apte School'),
            ('06', 'Janta Vidyalaya'),
            ('07', 'HOC Pillai'),
            ('08', 'Tungaratan'),
            ('09', 'PRIA'),
            ('10', 'Ritghar'),
            ('11', 'Nere School'),
            ('12', 'AKVP English Medium'),
            ('13', 'AKVP Marathi Medium'),
            ('14', 'AKVP Primary School English'),
            ('15', 'Pillai Global Academy'),
            ('16', 'Sanjeevani'),
            ('17', 'MES Public'),
            ('18', 'MES Dyanmandir'),
            ('19', 'CKT English Medium'),
            ('20', 'CKT Jr college'),
            ('21', 'Dew Drop School'),
            ('22', 'Loknete Ramsheth Thakur State Board'),
            ('23', 'Loknete Ramsheth Thakur CBSE'),
            ('24', "ST Xavier's school"),
            ('25', 'MNR'),
            ('26', 'Chatrapati Shivaji Vidyalaya'),
            ('27', 'New Horizons School'),
            ('28', 'ST Wilfred'),
            ('29', 'MNR Excellence'),
            ('30', 'Kendriya vidyalaya ONGC'),
            ('31', 'Kothari International'),
            ('32', 'SGT In school'),
            ('33', 'DAV'),
            ('34', 'ST Joseph High School'),
            ('35', 'Relience foundation School State Board'),
            ('36', 'Reliance foundation School CBSE Board')
        ]
        count = 0
        for code, name in schools_data:
            _, created = School.objects.get_or_create(code=code, defaults={'name': name})
            if created:
                count += 1
        messages.success(request, f"Successfully restored {count} default schools (Codes 01 to 36).")
        return redirect('dashboard:settings')

class AboutView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'dashboard/about.html')
