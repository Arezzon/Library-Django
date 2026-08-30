from django import forms
from library.forms_mixins import TailwindFormMixin
from .models import CustomUser, ROLE_VISITOR, ROLE_LIBRARIAN, ROLE_CHOICES


class RegistrationForm(TailwindFormMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
        label="Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
        label="Confirm Password"
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'middle_name', 'last_name', 'email', 'role']
        labels = {
            'first_name': 'First Name',
            'middle_name': 'Middle Name',
            'last_name': 'Last Name',
            'email': 'Email Address',
            'role': 'Register As',
        }
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'John'}),
            'middle_name': forms.TextInput(attrs={'placeholder': 'D.'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Doe'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("User with this email already exists.")
        return email

    def save(self, commit=True):
        user = CustomUser.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data.get('first_name', ''),
            middle_name=self.cleaned_data.get('middle_name', ''),
            last_name=self.cleaned_data.get('last_name', ''),
            role=self.cleaned_data.get('role', ROLE_VISITOR),
            is_active=True,
        )
        return user


class LoginForm(TailwindFormMixin, forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'})
    )


class UserUpdateForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'middle_name', 'last_name', 'role', 'is_active']
        labels = {
            'first_name': 'First Name',
            'middle_name': 'Middle Name',
            'last_name': 'Last Name',
            'role': 'Role',
            'is_active': 'Active Account (Access permitted)',
        }

