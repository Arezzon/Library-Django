from django import forms
from django.forms.utils import pretty_name

REQUIRED = forms.Field.default_error_messages["required"]


def plain_error_messages(name, field):
    """Replace Django's generic messages with ones that name the field and say how to fix
    it (FR-043). Messages a form sets itself are kept."""
    label = str(field.label or pretty_name(name))
    messages = field.error_messages
    if str(messages.get("required")) == str(REQUIRED):
        if isinstance(field.widget, forms.CheckboxInput):
            messages["required"] = f"Tick “{label}”."
        elif isinstance(field.widget, forms.SelectMultiple):
            messages["required"] = f"Choose at least one option in “{label}”."
        elif isinstance(field.widget, forms.Select):
            messages["required"] = f"Choose an option in “{label}”."
        else:
            messages["required"] = f"Enter {label.lower()}."
    # A model field's range validators raise these codes too, and a ModelForm replaces
    # their message with the form field's.
    if isinstance(field, forms.IntegerField):
        messages.setdefault("min_value", f"{label} must be %(limit_value)s or more.")
        messages.setdefault("max_value", f"{label} must be %(limit_value)s or less.")
    if getattr(field, "max_length", None) is not None:
        messages.setdefault(
            "max_length",
            f"{label} must be %(limit_value)d characters or fewer (it has %(show_value)d).",
        )


class TailwindFormMixin:
    """
    Mixin that automatically assigns clean, modern Tailwind CSS classes
    to all form widgets according to their input types, and gives every field
    plain error messages. ``has_required_fields`` tells the template to explain
    the required-field mark.
    """

    tailwind_input_class = (
        "w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl shadow-sm "
        "text-slate-900 placeholder-slate-400 text-base sm:text-sm focus:outline-none focus:ring-2 "
        "focus:ring-indigo-500 focus:border-indigo-500 transition duration-150"
    )
    tailwind_checkbox_class = (
        "w-4 h-4 sm:w-4 sm:h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 "
        "transition duration-150 cursor-pointer"
    )
    tailwind_select_class = (
        "w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl shadow-sm "
        "text-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 "
        "focus:border-indigo-500 transition duration-150"
    )
    tailwind_textarea_class = (
        "w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl shadow-sm "
        "text-slate-900 placeholder-slate-400 text-base sm:text-sm focus:outline-none focus:ring-2 "
        "focus:ring-indigo-500 focus:border-indigo-500 transition duration-150 resize-y"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_required_fields = any(
            field.required and not field.widget.is_hidden
            for field in self.fields.values()
        )
        for name, field in self.fields.items():
            plain_error_messages(name, field)
            widget = field.widget
            existing_class = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                cls = self.tailwind_checkbox_class
            elif isinstance(widget, (forms.SelectMultiple, forms.Select)):
                cls = self.tailwind_select_class
            elif isinstance(widget, forms.Textarea):
                cls = self.tailwind_textarea_class
                widget.attrs.setdefault("rows", 3)
            else:
                cls = self.tailwind_input_class

            widget.attrs["class"] = f"{cls} {existing_class}".strip()
