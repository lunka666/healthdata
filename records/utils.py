"""
Вспомогательные функции для работы с файлами показателей здоровья.

Формат — JSON (вариант задания №9).

Структура одной записи (HealthRecord) как обычного словаря Python:
{
    "patient_full_name": str,
    "birth_date": "YYYY-MM-DD",
    "blood_type": str,          # один из: A+ A- B+ B- AB+ AB- O+ O-
    "height_cm": int,
    "weight_kg": float,
    "systolic_bp": int,         # верхнее давление, мм рт. ст.
    "diastolic_bp": int,        # нижнее давление, мм рт. ст.
    "heart_rate": int,          # пульс, уд/мин
    "temperature_c": float,     # температура тела, °C
    "measurement_date": "YYYY-MM-DD",
    "symptoms": [str, str, ...],
}

Формат хранения на диске — всегда СПИСОК записей, даже если она одна:
{"records": [ {...}, {...} ]}

Такое единообразие упрощает чтение: одна и та же функция разбирает
и файл, созданный формой (в нём всегда 1 запись), и файл, загруженный
пользователем (в нём может быть несколько записей).
"""
import json
import uuid
import datetime as dt

ALLOWED_EXTENSIONS = {'.json'}

RECORD_FIELDS = (
    'patient_full_name', 'birth_date', 'blood_type', 'height_cm',
    'weight_kg', 'systolic_bp', 'diastolic_bp', 'heart_rate',
    'temperature_c', 'measurement_date', 'symptoms',
)


def safe_filename(extension: str = '.json') -> str:
    """
    Генерирует безопасное имя файла на сервере.

    Имя файла, присланное пользователем в форме загрузки, НИКОГДА
    не используется напрямую: в нём может быть "../../etc/passwd",
    null-байты, скрипты и т.п. Вместо этого мы всегда придумываем
    имя сами: метка времени + случайный uuid.
    """
    extension = extension.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f'Недопустимое расширение файла: {extension}')
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    unique = uuid.uuid4().hex[:12]
    return f'health_{timestamp}_{unique}{extension}'


# ---------------------------------------------------------------------------
# Словарь -> JSON (используется, когда мы САМИ создаём файл — после
# отправки формы, поэтому здесь можно не бояться вредоносного содержимого)
# ---------------------------------------------------------------------------

def records_to_json_bytes(records: list[dict]) -> bytes:
    payload = {'records': records}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


# ---------------------------------------------------------------------------
# JSON -> список словарей (используется при ЧТЕНИИ и при разборе
# ЗАГРУЖЕННЫХ пользователем файлов — здесь содержимое НЕ доверенное)
# ---------------------------------------------------------------------------

class DataFormatError(Exception):
    """Файл не соответствует ожидаемой структуре показателей здоровья."""


def parse_json_bytes(raw: bytes) -> list[dict]:
    try:
        data = json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataFormatError(f'Некорректный JSON: {exc}') from exc

    if isinstance(data, dict) and 'records' in data:
        items = data['records']
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        raise DataFormatError('Ожидался объект или список объектов с показателями')

    if not isinstance(items, list):
        raise DataFormatError('Поле "records" должно быть списком')

    result = []
    for item in items:
        if not isinstance(item, dict):
            raise DataFormatError('Каждая запись должна быть объектом (словарём)')
        result.append(item)
    return result


def parse_data_bytes(raw: bytes, extension: str) -> list[dict]:
    """Разбирает содержимое файла в зависимости от расширения."""
    extension = extension.lower()
    if extension == '.json':
        return parse_json_bytes(raw)
    raise DataFormatError(f'Неподдерживаемое расширение: {extension}. Разрешён только .json')
