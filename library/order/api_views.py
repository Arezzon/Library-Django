from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Order
from .serializers import OrderSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """CRUD: /api/v1/order/{id}?"""
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer


class UserOrderViewSet(viewsets.ModelViewSet):
    """CRUD: /api/v1/user/{user_id}/order/{id}?"""
    serializer_class = OrderSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        return Order.objects.filter(user_id=user_id).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        user_id = self.kwargs.get('user_id')
        data = request.data.copy()
        data['user'] = user_id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
