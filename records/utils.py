"""
Вспомогательные функции для работы с файлами показателей здоровья.

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
JSON: {"records": [ {...}, {...} ]}
XML:  <health_records><record>...</record><record>...</record></health_records>

Единый формат сильно упрощает чтение: одна и та же функция разбирает
и файл, созданный формой (в нём всегда 1 запись), и файл, загруженный
пользователем (в нём может быть несколько записей).
"""
import json
import uuid
import datetime as dt
import xml.etree.ElementTree as ET  # для ГЕНЕРАЦИИ xml — это безопасно

# Для РАЗБОРА чужих (untrusted) xml-файлов используем defusedxml.
# Обычный xml.etree.ElementTree.parse() уязвим к атакам вида
# "billion laughs" (xml-бомба через entity expansion) — вредоносный
# файл в пару килобайт может развернуться в гигабайты в памяти и
# положить сервер. defusedxml отключает такие возможности.
from defusedxml import ElementTree as SafeET

ALLOWED_EXTENSIONS = {'.json', '.xml'}

RECORD_FIELDS = (
    'patient_full_name', 'birth_date', 'blood_type', 'height_cm',
    'weight_kg', 'systolic_bp', 'diastolic_bp', 'heart_rate',
    'temperature_c', 'measurement_date', 'symptoms',
)

# Простые (не списочные) поля — их читаем как обычный текст тега.
SIMPLE_FIELDS = (
    'patient_full_name', 'birth_date', 'blood_type', 'height_cm',
    'weight_kg', 'systolic_bp', 'diastolic_bp', 'heart_rate',
    'temperature_c', 'measurement_date',
)


def safe_filename(extension: str) -> str:
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
# Словарь -> JSON / XML (используется, когда мы САМИ создаём файл — после
# отправки формы, поэтому здесь можно не бояться вредоносного содержимого)
# ---------------------------------------------------------------------------

def records_to_json_bytes(records: list[dict]) -> bytes:
    payload = {'records': records}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


def records_to_xml_bytes(records: list[dict]) -> bytes:
    root = ET.Element('health_records')
    for record in records:
        record_el = ET.SubElement(root, 'record')
        for field in SIMPLE_FIELDS:
            el = ET.SubElement(record_el, field)
            el.text = str(record.get(field, ''))
        symptoms_el = ET.SubElement(record_el, 'symptoms')
        for symptom in record.get('symptoms', []):
            s_el = ET.SubElement(symptoms_el, 'symptom')
            s_el.text = str(symptom)
    ET.indent(root, space='  ')
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8')


# ---------------------------------------------------------------------------
# JSON / XML -> список словарей (используется при ЧТЕНИИ и при разборе
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


def parse_xml_bytes(raw: bytes) -> list[dict]:
    try:
        root = SafeET.fromstring(raw)
    except Exception as exc:  # defusedxml поднимает разные типы ошибок
        raise DataFormatError(f'Некорректный XML: {exc}') from exc

    if root.tag == 'record':
        record_elements = [root]
    else:
        record_elements = root.findall('record')

    if not record_elements:
        raise DataFormatError('В XML не найдено ни одного тега <record>')

    result = []
    for record_el in record_elements:
        item = {}
        for field in SIMPLE_FIELDS:
            node = record_el.find(field)
            item[field] = node.text.strip() if node is not None and node.text else ''
        symptoms = []
        symptoms_el = record_el.find('symptoms')
        if symptoms_el is not None:
            for s_el in symptoms_el.findall('symptom'):
                if s_el.text:
                    symptoms.append(s_el.text.strip())
        item['symptoms'] = symptoms
        result.append(item)
    return result


def parse_data_bytes(raw: bytes, extension: str) -> list[dict]:
    """Разбирает содержимое файла в зависимости от расширения."""
    extension = extension.lower()
    if extension == '.json':
        return parse_json_bytes(raw)
    if extension == '.xml':
        return parse_xml_bytes(raw)
    raise DataFormatError(f'Неподдерживаемое расширение: {extension}')
