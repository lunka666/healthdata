"""
Единая функция проверки записи о показателях здоровья.

Используется в ДВУХ местах:
1. В форме ручного ввода (HealthRecordForm) — как дополнительная проверка
   "на всякий случай" после того, как Django Forms уже проверили типы.
2. При загрузке файла (upload_view) — там данные приходят из
   произвольного файла, и это единственная линия защиты от "мусора".

Диапазоны значений — это НЕ строгие медицинские нормы (нормальное давление
у разных людей отличается), а разумные физиологически возможные границы,
которые отсекают явно ошибочные/бессмысленные данные (например,
пульс "9999" или температуру "-40").
"""
import re
import datetime as dt

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё\s\-']+$")
MIN_YEAR = 1900
ALLOWED_BLOOD_TYPES = {'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'}


def _parse_date(value):
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value.strip())
    raise ValueError('не строка и не date')


def validate_record_dict(data: dict) -> list[str]:
    """Возвращает список текстов ошибок. Пустой список — данные валидны."""
    errors = []

    # --- ФИО пациента ------------------------------------------------------
    name = data.get('patient_full_name')
    if not isinstance(name, str) or not name.strip():
        errors.append('Поле "ФИО пациента" обязательно и должно быть непустой строкой')
    else:
        name = name.strip()
        if len(name) > 100:
            errors.append('ФИО пациента длиннее 100 символов')
        if not NAME_RE.match(name):
            errors.append('ФИО пациента должно содержать только буквы, пробелы и дефис')

    # --- дата рождения ------------------------------------------------
    birth_date = data.get('birth_date')
    if not birth_date:
        errors.append('Поле "Дата рождения" обязательно')
    else:
        try:
            parsed = _parse_date(birth_date)
        except ValueError:
            errors.append('Дата рождения должна быть в формате ГГГГ-ММ-ДД')
            parsed = None
        if parsed is not None:
            today = dt.date.today()
            if parsed > today:
                errors.append('Дата рождения не может быть в будущем')
            if parsed.year < MIN_YEAR:
                errors.append(f'Дата рождения не может быть раньше {MIN_YEAR} года')

    # --- дата измерения -----------------------------------------------
    measurement_date = data.get('measurement_date')
    if not measurement_date:
        errors.append('Поле "Дата измерения" обязательно')
    else:
        try:
            m_parsed = _parse_date(measurement_date)
            if m_parsed > dt.date.today():
                errors.append('Дата измерения не может быть в будущем')
        except ValueError:
            errors.append('Дата измерения должна быть в формате ГГГГ-ММ-ДД')

    # --- группа крови -------------------------------------------------
    blood_type = data.get('blood_type')
    if blood_type not in ALLOWED_BLOOD_TYPES:
        errors.append(
            'Группа крови должна быть одной из: ' + ', '.join(sorted(ALLOWED_BLOOD_TYPES))
        )

    # --- числовые физиологические показатели --------------------------
    numeric_checks = (
        ('height_cm', 'Рост', 50, 250),
        ('weight_kg', 'Вес', 2, 300),
        ('systolic_bp', 'Верхнее давление', 60, 250),
        ('diastolic_bp', 'Нижнее давление', 30, 150),
        ('heart_rate', 'Пульс', 20, 250),
        ('temperature_c', 'Температура тела', 30, 45),
    )
    numeric_values = {}
    for field, label, lo, hi in numeric_checks:
        value = data.get(field)
        try:
            num = float(value)
            numeric_values[field] = num
            if not (lo <= num <= hi):
                errors.append(f'"{label}" должен(-о) быть в диапазоне от {lo} до {hi}')
        except (TypeError, ValueError):
            errors.append(f'"{label}" должен(-о) быть числом')

    # --- логическая проверка: верхнее давление должно быть больше нижнего
    if 'systolic_bp' in numeric_values and 'diastolic_bp' in numeric_values:
        if numeric_values['systolic_bp'] <= numeric_values['diastolic_bp']:
            errors.append('Верхнее давление должно быть больше нижнего')

    # --- симптомы -------------------------------------------------------
    symptoms = data.get('symptoms', [])
    if symptoms is None:
        symptoms = []
    if not isinstance(symptoms, list):
        errors.append('Поле "Симптомы" должно быть списком строк')
    else:
        if len(symptoms) > 30:
            errors.append('Слишком много симптомов (максимум 30)')
        for item in symptoms:
            if not isinstance(item, str) or len(item) > 200:
                errors.append('Каждый симптом должен быть строкой не длиннее 200 символов')
                break

    return errors
