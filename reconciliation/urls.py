from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/runs', views.ReconciliationViewSet, basename='run')

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('run/<int:run_id>/', views.run_details, name='run_details'),
    path('', include(router.urls)),
]
