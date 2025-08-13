from django.urls import path
from . import views

app_name = 'quotes'

urlpatterns = [
    path('', views.quote_list, name='list'),
    path('upload/', views.upload_quote, name='upload'),
    path('<int:quote_id>/', views.quote_detail, name='detail'),
    path('<int:quote_id>/status/', views.quote_status, name='status'),
    path('<int:quote_id>/rematch/', views.rematch_quote, name='rematch'),
]
