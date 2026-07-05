from django.shortcuts import render, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from .models import Result
from .ranking import calculate_dense_ranks
from schools.models import School

class ResultListView(LoginRequiredMixin, ListView):
    model = Result
    template_name = 'results/result_list.html'
    context_object_name = 'results'
    paginate_by = 50

    def get_queryset(self):
        queryset = Result.objects.filter(submission__is_accepted=True).select_related('participant', 'participant__school').order_by('-score', 'participant__roll_number')
        
        # Search
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(participant__roll_number__icontains=q)
            
        # Filters
        school_id = self.request.GET.get('school', '')
        if school_id:
            queryset = queryset.filter(participant__school_id=school_id)
            
        group = self.request.GET.get('group', '')
        if group:
            queryset = queryset.filter(participant__group=group)
            
        paper_set = self.request.GET.get('set', '')
        if paper_set:
            queryset = queryset.filter(participant__paper_set=paper_set)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['schools'] = School.objects.all().order_by('code')
        
        # Add ranks dynamically to the paginated list for display
        all_results = list(Result.objects.filter(submission__is_accepted=True).select_related('participant').order_by('-score'))
        calculate_dense_ranks(all_results)
        # Map result ID to its rank
        rank_map = {r.pk: r.rank for r in all_results}
        
        for result in context['results']:
            result.rank = rank_map.get(result.pk, '—')
            
        # Preserve query parameters
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        context['query_params'] = query_params.urlencode()
        return context

class ResultDetailView(LoginRequiredMixin, DetailView):
    model = Result
    template_name = 'results/result_detail.html'
    context_object_name = 'result'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = self.get_object()
        
        # Calculate rank within their group
        group_results = list(Result.objects.filter(
            submission__is_accepted=True,
            participant__group=result.participant.group
        ).select_related('participant').order_by('-score'))
        
        calculate_dense_ranks(group_results)
        
        # Find this participant's rank
        for r in group_results:
            if r.pk == result.pk:
                context['group_rank'] = r.rank
                break
                
        context['total_in_group'] = len(group_results)
        return context

class RankingsView(LoginRequiredMixin, View):
    def get(self, request):
        # 1. Junior Rankings
        junior_results = list(Result.objects.filter(
            submission__is_accepted=True,
            participant__group='JUNIOR'
        ).select_related('participant', 'participant__school').order_by('-score', 'participant__roll_number'))
        calculate_dense_ranks(junior_results)
        
        # 2. Senior Rankings
        senior_results = list(Result.objects.filter(
            submission__is_accepted=True,
            participant__group='SENIOR'
        ).select_related('participant', 'participant__school').order_by('-score', 'participant__roll_number'))
        calculate_dense_ranks(senior_results)
        
        # 3. Overall Rankings
        overall_results = list(Result.objects.filter(
            submission__is_accepted=True
        ).select_related('participant', 'participant__school').order_by('-score', 'participant__roll_number'))
        calculate_dense_ranks(overall_results)
        
        # 4. School-wise Rankings
        schools = School.objects.all().order_by('code')
        selected_school_id = request.GET.get('school', '')
        
        school_junior_ranked = []
        school_senior_ranked = []
        selected_school = None
        
        if selected_school_id:
            selected_school = get_object_or_404(School, pk=selected_school_id)
            # Rank Juniors within this school
            school_junior = list(Result.objects.filter(
                submission__is_accepted=True,
                participant__school=selected_school,
                participant__group='JUNIOR'
            ).select_related('participant').order_by('-score', 'participant__roll_number'))
            school_junior_ranked = calculate_dense_ranks(school_junior)
            
            # Rank Seniors within this school
            school_senior = list(Result.objects.filter(
                submission__is_accepted=True,
                participant__school=selected_school,
                participant__group='SENIOR'
            ).select_related('participant').order_by('-score', 'participant__roll_number'))
            school_senior_ranked = calculate_dense_ranks(school_senior)
        elif schools.exists():
            # Default to first school
            selected_school = schools[0]
            school_junior = list(Result.objects.filter(
                submission__is_accepted=True,
                participant__school=selected_school,
                participant__group='JUNIOR'
            ).select_related('participant').order_by('-score', 'participant__roll_number'))
            school_junior_ranked = calculate_dense_ranks(school_junior)
            
            school_senior = list(Result.objects.filter(
                submission__is_accepted=True,
                participant__school=selected_school,
                participant__group='SENIOR'
            ).select_related('participant').order_by('-score', 'participant__roll_number'))
            school_senior_ranked = calculate_dense_ranks(school_senior)
            
        context = {
            'junior_rankings': junior_results[:50],  # Show top 50 in view, full list available via PDF
            'senior_rankings': senior_results[:50],
            'overall_rankings': overall_results[:100],
            'schools': schools,
            'selected_school': selected_school,
            'school_junior_rankings': school_junior_ranked,
            'school_senior_rankings': school_senior_ranked,
            'active_tab': request.GET.get('tab', 'junior')
        }
        return render(request, 'results/rankings.html', context)
