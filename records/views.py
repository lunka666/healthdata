import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect

from .forms import HealthRecordForm, UploadFileForm
from .validators import validate_record_dict
from .utils import (
    safe_filename,
    records_to_json_bytes,
    records_to_xml_bytes,
    parse_data_bytes,
    DataFormatError,
)


def home(request):
    json_count = len([f for f in os.listdir(settings.DATA_JSON_DIR) if f.endswith('.json')])
    xml_count = len([f for f in os.listdir(settings.DATA_XML_DIR) if f.endswith('.xml')])
    return render(request, 'records/home.html', {
        'json_count': json_count,
        'xml_count': xml_count,
    })


def create_record(request):
    """Шаг 1 требования: ввод данных через форму -> сохранение в JSON/XML."""
    if request.method == 'POST':
        form = HealthRecordForm(request.POST)
        if form.is_valid():
            record = form.to_record_dict()

            # Доп. проверка той же функцией, что используется для файлов —
            # чтобы правила валидации были гарантированно одинаковы.
            errors = validate_record_dict(record)
            if errors:
                for err in errors:
                    messages.error(request, err)
                return render(request, 'records/create_form.html', {'form': form})

            file_format = form.cleaned_data['file_format']
            if file_format == 'json':
                filename = safe_filename('.json')
                content = records_to_json_bytes([record])
                target_dir = settings.DATA_JSON_DIR
            else:
                filename = safe_filename('.xml')
                content = records_to_xml_bytes([record])
                target_dir = settings.DATA_XML_DIR

            with open(target_dir / filename, 'wb') as fh:
                fh.write(content)

            messages.success(request, f'Данные сохранены в файл "{filename}"')
            return redirect('records:create')
        # форма невалидна — Django сам покажет ошибки по полям в шаблоне
    else:
        form = HealthRecordForm()

    return render(request, 'records/create_form.html', {'form': form})


def upload_file(request):
    """
    Шаг 2 требования: загрузка готового файла с проверкой валидности.
    Если файл невалиден — сообщение и удаление файла с диска.
    """
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data['data_file']
            _, ext = os.path.splitext(uploaded.name)
            ext = ext.lower()

            # Имя на диске генерируем сами — имени пользователя не доверяем.
            filename = safe_filename(ext)
            target_dir = settings.DATA_JSON_DIR if ext == '.json' else settings.DATA_XML_DIR
            file_path = target_dir / filename

            # Сохраняем файл на диск потоково (чанками), чтобы не грузить
            # в память сразу целиком, если файл большой.
            with open(file_path, 'wb') as fh:
                for chunk in uploaded.chunks():
                    fh.write(chunk)

            # Теперь проверяем содержимое только что сохранённого файла.
            try:
                with open(file_path, 'rb') as fh:
                    raw = fh.read()
                records = parse_data_bytes(raw, ext)

                all_errors = []
                for idx, record in enumerate(records, start=1):
                    for err in validate_record_dict(record):
                        all_errors.append(f'Запись №{idx}: {err}')

                if all_errors:
                    raise DataFormatError('; '.join(all_errors))

            except DataFormatError as exc:
                # Файл невалиден — удаляем его и сообщаем пользователю.
                if file_path.exists():
                    os.remove(file_path)
                messages.error(
                    request,
                    f'Файл не прошёл проверку и был удалён. Причина: {exc}',
                )
                return redirect('records:upload')

            messages.success(
                request,
                f'Файл успешно загружен и прошёл проверку. '
                f'Сохранён на сервере как "{filename}" ({len(records)} записей).',
            )
            return redirect('records:upload')
    else:
        form = UploadFileForm()

    return render(request, 'records/upload_form.html', {'form': form})


def view_data(request):
    """
    Шаг 3 требования: чтение и отображение содержимого всех файлов.
    Если файлов нет — соответствующее сообщение.
    """
    records = []
    broken_files = []

    for directory, ext in ((settings.DATA_JSON_DIR, '.json'), (settings.DATA_XML_DIR, '.xml')):
        for filename in sorted(os.listdir(directory)):
            file_path = directory / filename
            if not file_path.is_file() or not filename.lower().endswith(ext):
                continue  # пропускаем служебные файлы вроде .gitkeep
            try:
                with open(file_path, 'rb') as fh:
                    raw = fh.read()
                items = parse_data_bytes(raw, ext)
                for item in items:
                    records.append({
                        'source_file': filename,
                        'file_format': ext.lstrip('.').upper(),
                        'patient_full_name': item.get('patient_full_name', ''),
                        'birth_date': item.get('birth_date', ''),
                        'blood_type': item.get('blood_type', ''),
                        'height_cm': item.get('height_cm', ''),
                        'weight_kg': item.get('weight_kg', ''),
                        'systolic_bp': item.get('systolic_bp', ''),
                        'diastolic_bp': item.get('diastolic_bp', ''),
                        'heart_rate': item.get('heart_rate', ''),
                        'temperature_c': item.get('temperature_c', ''),
                        'measurement_date': item.get('measurement_date', ''),
                        'symptoms': item.get('symptoms', []),
                    })
            except DataFormatError as exc:
                # Файл повреждён (например, кто-то отредактировал его
                # руками на диске) — не роняем страницу, а просто
                # показываем предупреждение и пропускаем этот файл.
                broken_files.append((filename, str(exc)))

    no_files = not records and not broken_files

    return render(request, 'records/view_data.html', {
        'records': records,
        'broken_files': broken_files,
        'no_files': no_files,
    })
