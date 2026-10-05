import os
import datetime as dt

from django import forms
from django.conf import settings

from .validators import NAME_RE, ALLOWED_BLOOD_TYPES


class HealthRecordForm(forms.Form):
    """Форма ручного ввода показателей здоровья пациента."""

    BLOOD_TYPE_CHOICES = [(bt, bt) for bt in sorted(ALLOWED_BLOOD_TYPES)]

    patient_full_name = forms.CharField(
        label='ФИО пациента', max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    birth_date = forms.DateField(
        label='Дата рождения',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    blood_type = forms.ChoiceField(
        label='Группа крови', choices=BLOOD_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    height_cm = forms.IntegerField(
        label='Рост (см)', min_value=50, max_value=250,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    weight_kg = forms.FloatField(
        label='Вес (кг)', min_value=2, max_value=300,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
    )
    systolic_bp = forms.IntegerField(
        label='Верхнее давление (мм рт. ст.)', min_value=60, max_value=250,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    diastolic_bp = forms.IntegerField(
        label='Нижнее давление (мм рт. ст.)', min_value=30, max_value=150,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    heart_rate = forms.IntegerField(
        label='Пульс (уд/мин)', min_value=20, max_value=250,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    temperature_c = forms.FloatField(
        label='Температура тела (°C)', min_value=30, max_value=45,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
    )
    measurement_date = forms.DateField(
        label='Дата измерения',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    symptoms = forms.CharField(
        label='Симптомы (каждый с новой строки)', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def clean_patient_full_name(self):
        value = self.cleaned_data['patient_full_name'].strip()
        if not NAME_RE.match(value):
            raise forms.ValidationError('Допустимы только буквы, пробелы и дефис')
        return value

    def clean_birth_date(self):
        value = self.cleaned_data['birth_date']
        if value > dt.date.today():
            raise forms.ValidationError('Дата рождения не может быть в будущем')
        if value.year < 1900:
            raise forms.ValidationError('Дата рождения не может быть раньше 1900 года')
        return value

    def clean_measurement_date(self):
        value = self.cleaned_data['measurement_date']
        if value > dt.date.today():
            raise forms.ValidationError('Дата измерения не может быть в будущем')
        return value

    def clean_symptoms(self):
        raw = self.cleaned_data.get('symptoms', '')
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(items) > 30:
            raise forms.ValidationError('Слишком много симптомов (максимум 30)')
        for item in items:
            if len(item) > 200:
                raise forms.ValidationError('Каждый симптом должен быть короче 200 символов')
        return items

    def clean(self):
        cleaned = super().clean()
        systolic = cleaned.get('systolic_bp')
        diastolic = cleaned.get('diastolic_bp')
        if systolic is not None and diastolic is not None and systolic <= diastolic:
            raise forms.ValidationError('Верхнее давление должно быть больше нижнего')
        return cleaned

    def to_record_dict(self) -> dict:
        """Собирает провалидированные данные формы в единый словарь HealthRecord."""
        data = self.cleaned_data
        return {
            'patient_full_name': data['patient_full_name'],
            'birth_date': data['birth_date'].isoformat(),
            'blood_type': data['blood_type'],
            'height_cm': data['height_cm'],
            'weight_kg': data['weight_kg'],
            'systolic_bp': data['systolic_bp'],
            'diastolic_bp': data['diastolic_bp'],
            'heart_rate': data['heart_rate'],
            'temperature_c': data['temperature_c'],
            'measurement_date': data['measurement_date'].isoformat(),
            'symptoms': data['symptoms'],
        }


class UploadFileForm(forms.Form):
    """Форма загрузки готового JSON файла на сервер."""

    data_file = forms.FileField(label='Файл с данными (.json)')

    def clean_data_file(self):
        f = self.cleaned_data['data_file']

        # 1. Расширение проверяем, но НИКОГДА не используем исходное имя
        #    файла для сохранения на диске — только для определения формата.
        _, ext = os.path.splitext(f.name)
        ext = ext.lower()
        if ext != '.json':
            raise forms.ValidationError(
                'Разрешены только файлы с расширением .json'
            )

        # 2. Ограничение размера — защита от заливки огромных файлов.
        if f.size > settings.MAX_UPLOAD_SIZE:
            max_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
            raise forms.ValidationError(f'Размер файла не должен превышать {max_mb:.0f} МБ')

        return f
