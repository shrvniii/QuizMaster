from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, Http404
from django.contrib import messages
from .pdf_builder import build_individual_slip_pdf, build_school_results_pdf, build_ranking_list_pdf
from .excel_builder import build_rankings_excel
from scanner.omr_generator import (
    generate_blank_omr_pdf, 
    generate_personalized_omr_pdf, 
    generate_personalized_omr_sheets_pdf,
    generate_school_omr_sheets_pdf
)
from results.models import Result
from scanner.models import OMRSubmission
from results.ranking import calculate_dense_ranks
from participants.models import Participant
from schools.models import School
import tempfile
import os

class ReportListView(LoginRequiredMixin, View):
    def get(self, request):
        schools = School.objects.all().order_by('name')
        participants_with_results = Participant.objects.filter(
            omr_submission__status='EVALUATED'
        ).order_by('roll_number')
        
        school_codes = [f"{i:02d}" for i in range(1, 51)]
        
        context = {
            'schools': schools,
            'participants': participants_with_results,
            'school_codes': school_codes,
        }
        return render(request, 'reports/report_list.html', context)

class IndividualReportDownloadView(LoginRequiredMixin, View):
    def get(self, request, participant_id):
        participant = get_object_or_404(Participant, pk=participant_id)
        if not hasattr(participant, 'omr_submission') or participant.omr_submission.status != 'EVALUATED':
            raise Http404("No evaluated result found for this participant.")
            
        result = participant.omr_submission.result
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="result_slip_{participant.roll_number}.pdf"'
        
        build_individual_slip_pdf(result, response)
        return response

class SchoolReportDownloadView(LoginRequiredMixin, View):
    def get(self, request, school_id):
        school = get_object_or_404(School, pk=school_id)
        
        # Get all results for this school, sorted by group and score
        results = list(Result.objects.filter(
            submission__is_accepted=True,
            participant__school=school
        ).select_related('participant').order_by('participant__group', '-score', 'participant__roll_number'))
        
        # Split and calculate ranks within school categories
        juniors = [r for r in results if r.participant.group == 'JUNIOR']
        seniors = [r for r in results if r.participant.group == 'SENIOR']
        calculate_dense_ranks(juniors)
        calculate_dense_ranks(seniors)
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="school_report_{school.name.replace(" ", "_")}.pdf"'
        
        build_school_results_pdf(school, results, response)
        return response

class RankingReportDownloadView(LoginRequiredMixin, View):
    def get(self, request, group):
        group_upper = group.upper()
        if group_upper not in ['JUNIOR', 'SENIOR']:
            raise Http404("Invalid group.")
            
        results = list(Result.objects.filter(
            submission__is_accepted=True,
            participant__group=group_upper
        ).select_related('participant', 'participant__school').order_by('-score', 'participant__roll_number'))
        
        calculate_dense_ranks(results)
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{group_upper.lower()}_rankings.pdf"'
        
        build_ranking_list_pdf(group_upper, results, response)
        return response

class CSVReportDownloadView(LoginRequiredMixin, View):
    def get(self, request):
        submissions = OMRSubmission.objects.filter(is_accepted=True).select_related(
            'participant', 
            'participant__school', 
            'result',
            'operator'
        ).all()
        
        def sort_key(s):
            p = s.participant
            school_code = p.school.code if (p and p.school) else 'ZZ'
            roll_number = p.roll_number if p else 'ZZZZZ'
            return (school_code, roll_number)
            
        submissions = sorted(submissions, key=sort_key)
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="bkj_qms_standings.xlsx"'
        
        build_rankings_excel(submissions, response)
        return response

class BlankOMRSheetDownloadView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="blank_omr_sheet.pdf"'
        
        # Generate the PDF into a temporary file, then write it to the response
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            generate_blank_omr_pdf(tmp_path)
            with open(tmp_path, 'rb') as f:
                response.write(f.read())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return response

class PersonalizedOMRSheetDownloadView(LoginRequiredMixin, View):
    def get(self, request, participant_id):
        participant = get_object_or_404(Participant, pk=participant_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="omr_{participant.roll_number}.pdf"'
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            generate_personalized_omr_pdf(tmp_path, participant)
            with open(tmp_path, 'rb') as f:
                response.write(f.read())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return response

class SchoolOMRSheetsDownloadView(LoginRequiredMixin, View):
    def get(self, request, school_id):
        school = get_object_or_404(School, pk=school_id)
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="School_{school.code}.pdf"'
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            generate_school_omr_sheets_pdf(tmp_path, school)
            with open(tmp_path, 'rb') as f:
                response.write(f.read())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return response


class PregeneratedOMRDownloadView(LoginRequiredMixin, View):
    def get(self, request, school_code, group, start, end):
        # Validate school code is a 2-digit numeric code between 01 and 50
        if not school_code.isdigit() or len(school_code) != 2:
            raise Http404("Invalid school code format. Must be a 2-digit number.")
            
        code_val = int(school_code)
        if not (1 <= code_val <= 50):
            raise Http404("School code must be between 01 and 50.")
            
        group_upper = group.upper()
        if group_upper not in ['JUNIOR', 'SENIOR']:
            raise Http404("Group must be either JUNIOR or SENIOR.")
            
        # Validate ranges
        if group_upper == 'JUNIOR':
            if not (1 <= start <= end <= 499):
                raise Http404("Invalid Junior range. Must be within 001 and 499.")
        else:
            if not (500 <= start <= end <= 999):
                raise Http404("Invalid Senior range. Must be within 500 and 999.")
                
        # Limit batch size to 100 pages to avoid timeouts
        if (end - start + 1) > 100:
            raise Http404("Batch size cannot exceed 100 pages.")
            
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="School_{school_code}_{group_upper.lower()}_{start}_to_{end}.pdf"'
        
        # Import drawing helpers dynamically to prevent circular imports
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from scanner.omr_generator import draw_omr_sheet_on_canvas, MockParticipant
        from schools.models import School
        
        try:
            school_obj = School.objects.get(code=school_code)
        except School.DoesNotExist:
            school_name = f"School (Code: {school_code})"
            school_obj = School(code=school_code, name=school_name)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            c = canvas.Canvas(tmp_path, pagesize=A4)
            for r in range(start, end + 1):
                roll_number = f"{school_code}{r:03d}"
                p = MockParticipant(roll_number, school_obj, group_upper)
                draw_omr_sheet_on_canvas(c, p)
                c.showPage()
            c.save()
            
            with open(tmp_path, 'rb') as f:
                response.write(f.read())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return response
