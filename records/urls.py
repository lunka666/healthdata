from django.urls import path
from . import views

app_name = 'records'

urlpatterns = [
    path('', views.home, name='home'),
    path('create/', views.create_record, name='create'),
    path('upload/', views.upload_file, name='upload'),
    path('data/', views.view_data, name='view_data'),
]
