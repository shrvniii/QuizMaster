from django.urls import path
from .views import (
    ReportListView, 
    IndividualReportDownloadView, 
    SchoolReportDownloadView, 
    RankingReportDownloadView, 
    CSVReportDownloadView,
    BlankOMRSheetDownloadView,
    PersonalizedOMRSheetDownloadView,
    SchoolOMRSheetsDownloadView,
    PregeneratedOMRDownloadView
)

app_name = 'reports'

urlpatterns = [
    path('', ReportListView.as_view(), name='list'),
    path('download/individual/<int:participant_id>/', IndividualReportDownloadView.as_view(), name='individual_download'),
    path('download/school/<int:school_id>/', SchoolReportDownloadView.as_view(), name='school_download'),
    path('download/ranking/<str:group>/', RankingReportDownloadView.as_view(), name='ranking_download'),
    path('download/csv/', CSVReportDownloadView.as_view(), name='csv_download'),
    path('download/blank-omr/', BlankOMRSheetDownloadView.as_view(), name='blank_omr'),
    path('download/personalized-omr/<int:participant_id>/', PersonalizedOMRSheetDownloadView.as_view(), name='personalized_omr'),
    path('download/school-omr/<int:school_id>/', SchoolOMRSheetsDownloadView.as_view(), name='school_omr'),
    path('download/pregenerated-omr/<str:school_code>/<str:group>/<int:start>/<int:end>/', PregeneratedOMRDownloadView.as_view(), name='download_pregenerated_omr'),
]
