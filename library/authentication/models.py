import datetime

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

ROLE_VISITOR = 0
ROLE_LIBRARIAN = 1

ROLE_CHOICES = (
    (ROLE_VISITOR, 'visitor'),
    (ROLE_LIBRARIAN, 'librarian'),
)


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', ROLE_LIBRARIAN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser):
    """
        This class represents a basic user. \n
        Attributes:
        -----------
        param first_name: Describes first name of the user
        type first_name: str max length=20
        param last_name: Describes last name of the user
        type last_name: str max length=20
        param middle_name: Describes middle name of the user
        type middle_name: str max length=20
        param email: Describes the email of the user
        type email: str, unique, max length=100
        param password: Describes the password of the user
        type password: str
        param created_at: Describes the date when the user was created. Can't be changed.
        type created_at: int (timestamp)
        param updated_at: Describes the date when the user was modified
        type updated_at: int (timestamp)
        param role: user role, default role (0, 'visitor')
        type updated_at: int (choices)
        param is_active: user role, default value False
        type updated_at: bool
    """
    ROLE_VISITOR = ROLE_VISITOR
    ROLE_LIBRARIAN = ROLE_LIBRARIAN

    FIRST_NAME_MAX_LEN = 20
    LAST_NAME_MAX_LEN = 20
    MIDDLE_NAME_MAX_LEN = 20
    EMAIL_MAX_LEN = 100
    PASSWORD_MAX_LEN = 255
    EMAIL_PARTS_COUNT = 2

    first_name = models.CharField(max_length=FIRST_NAME_MAX_LEN, default=None)
    last_name = models.CharField(max_length=LAST_NAME_MAX_LEN, default=None)
    middle_name = models.CharField(max_length=MIDDLE_NAME_MAX_LEN, default=None)
    email = models.CharField(max_length=EMAIL_MAX_LEN, unique=True, default=None)
    password = models.CharField(default=None, max_length=PASSWORD_MAX_LEN)
    created_at = models.DateTimeField(editable=False, auto_now=datetime.datetime.now())
    updated_at = models.DateTimeField(auto_now=datetime.datetime.now())
    role = models.IntegerField(choices=ROLE_CHOICES, default=ROLE_VISITOR)
    is_active = models.BooleanField(default=False)
    id = models.AutoField(primary_key=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'middle_name']
    objects = CustomUserManager()

    @property
    def is_librarian(self):
        return self.role == self.ROLE_LIBRARIAN

    @property
    def is_visitor(self):
        return self.role == self.ROLE_VISITOR

    @property
    def is_staff(self):
        """Allows access to admin panel for librarians"""
        return self.role == self.ROLE_LIBRARIAN

    @is_staff.setter
    def is_staff(self, value):
        if value:
            self.role = self.ROLE_LIBRARIAN

    @property
    def is_superuser(self):
        """Grants all superuser permissions to librarians"""
        return self.role == self.ROLE_LIBRARIAN

    @is_superuser.setter
    def is_superuser(self, value):
        if value:
            self.role = self.ROLE_LIBRARIAN

    def has_perm(self, perm, obj=None):
        """Checks permissions for a specific action"""
        return self.role == self.ROLE_LIBRARIAN

    def has_module_perms(self, app_label):
        """Checks permissions for an app/section in the admin panel"""
        return self.role == self.ROLE_LIBRARIAN

    def __str__(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name} ({self.email})"
        return self.email

    def __repr__(self):
        """
        This magic method is redefined to show class and id of CustomUser object.
        :return: class, id
        """
        return f"{CustomUser.__name__}(id={self.id})"

    @staticmethod
    def get_by_id(user_id):
        """
        :param user_id: SERIAL: the id of a user to be found in the DB
        :return: user object or None if a user with such ID does not exist
        """
        custom_user = CustomUser.objects.filter(id=user_id).first()
        return custom_user if custom_user else None

    @staticmethod
    def get_by_email(email):
        """
        Returns user by email
        :param email: email by which we need to find the user
        :type email: str
        :return: user object or None if a user with such ID does not exist
        """
        custom_user = CustomUser.objects.filter(email=email).first()
        return custom_user if custom_user else None

    @staticmethod
    def delete_by_id(user_id):
        """
        :param user_id: an id of a user to be deleted
        :type user_id: int
        :return: True if object existed in the db and was removed or False if it didn't exist
        """
        user_to_delete = CustomUser.objects.filter(id=user_id).first()
        if user_to_delete:
            CustomUser.objects.filter(id=user_id).delete()
            return True
        return False

    @staticmethod
    def create(email, password, first_name=None, middle_name=None, last_name=None):
        """
        :param first_name: first name of a user
        :type first_name: str
        :param middle_name: middle name of a user
        :type middle_name: str
        :param last_name: last name of a user
        :type last_name: str
        :param email: email of a user
        :type email: str
        :param password: password of a user
        :type password: str
        :return: a new user object which is also written into the DB
        """
        if (
            len(first_name) <= CustomUser.FIRST_NAME_MAX_LEN
            and len(middle_name) <= CustomUser.MIDDLE_NAME_MAX_LEN
            and len(last_name) <= CustomUser.LAST_NAME_MAX_LEN
            and len(email) <= CustomUser.EMAIL_MAX_LEN
            and len(email.split('@')) == CustomUser.EMAIL_PARTS_COUNT
            and len(CustomUser.objects.filter(email=email)) == 0
        ):
            custom_user = CustomUser(email=email, password=password, first_name=first_name, middle_name=middle_name,
                                     last_name=last_name)
            custom_user.save()
            return custom_user
        return None

    def to_dict(self):
        """
        :return: user id, user first_name, user middle_name, user last_name,
                 user email, user password, user updated_at, user created_at, user is_active
        :Example:
        | {
        |   'id': 8,
        |   'first_name': 'fn',
        |   'middle_name': 'mn',
        |   'last_name': 'ln',
        |   'email': 'ln@mail.com',
        |   'created_at': 1509393504,
        |   'updated_at': 1509402866,
        |   'role': 0
        |   'is_active:' True
        | }
        """
        return {'id': self.id,
                'first_name': f'{self.first_name}',
                'middle_name': f'{self.middle_name}',
                'last_name': f'{self.last_name}',
                'email': f'{self.email}',
                'created_at': int(self.created_at.timestamp()),
                'updated_at': int(self.updated_at.timestamp()),
                'role': self.role,
                'is_active': self.is_active}

    def update(self,
               first_name=None,
               last_name=None,
               middle_name=None,
               password=None,
               role=None,
               is_active=None):
        """
        Updates user profile in the database with the specified parameters.\n
        :param first_name: first name of a user
        :type first_name: str
        :param middle_name: middle name of a user
        :type middle_name: str
        :param last_name: last name of a user
        :type last_name: str
        :param password: password of a user
        :type password: str
        :param role: role id
        :type role: int
        :param is_active: activation state
        :type is_active: bool
        :return: None
        """
        user_to_update = CustomUser.objects.filter(email=self.email).first()
        if first_name != None and len(first_name) <= CustomUser.FIRST_NAME_MAX_LEN:
            user_to_update.first_name = first_name
        if last_name != None and len(last_name) <= CustomUser.LAST_NAME_MAX_LEN:
            user_to_update.last_name = last_name
        if middle_name != None and len(middle_name) <= CustomUser.MIDDLE_NAME_MAX_LEN:
            user_to_update.middle_name = middle_name
        if password != None:
            user_to_update.password = password
        if role != None:
            user_to_update.role = role
        if is_active != None:
            user_to_update.is_active = is_active
        user_to_update.save()

    @staticmethod
    def get_all():
        """
        returns data for json request with QuerySet of all users
        """
        return CustomUser.objects.all()

    def get_role_name(self):
        """
        returns str role name
        """
        return dict(ROLE_CHOICES).get(self.role, str(self.role))
