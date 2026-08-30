from django import forms


class TailwindFormMixin:
    """
    Mixin that automatically assigns clean, modern Tailwind CSS classes
    to all form widgets according to their input types.
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
        for field_name, field in self.fields.items():
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
