import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect

from .forms import HealthRecordForm, UploadFileForm
from .validators import validate_record_dict
from .utils import (
    safe_filename,
    records_to_json_bytes,
    parse_data_bytes,
    DataFormatError,
)


def home(request):
    json_count = len([f for f in os.listdir(settings.DATA_JSON_DIR) if f.endswith('.json')])
    return render(request, 'records/home.html', {
        'json_count': json_count,
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

            filename = safe_filename('.json')
            content = records_to_json_bytes([record])

            with open(settings.DATA_JSON_DIR / filename, 'wb') as fh:
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

            # Имя на диске генерируем сами — имени пользователя не доверяем.
            # Расширение здесь всегда '.json' — это уже проверено в
            # UploadFileForm.clean_data_file(), но для читаемости кода
            # явно укажем формат при генерации имени.
            filename = safe_filename('.json')
            file_path = settings.DATA_JSON_DIR / filename

            # Сохраняем файл на диск потоково (чанками), чтобы не грузить
            # в память сразу целиком, если файл большой.
            with open(file_path, 'wb') as fh:
                for chunk in uploaded.chunks():
                    fh.write(chunk)

            # Теперь проверяем содержимое только что сохранённого файла.
            try:
                with open(file_path, 'rb') as fh:
                    raw = fh.read()
                records = parse_data_bytes(raw, '.json')

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

    directory = settings.DATA_JSON_DIR
    for filename in sorted(os.listdir(directory)):
        file_path = directory / filename
        if not file_path.is_file() or not filename.lower().endswith('.json'):
            continue  # пропускаем служебные файлы вроде .gitkeep
        try:
            with open(file_path, 'rb') as fh:
                raw = fh.read()
            items = parse_data_bytes(raw, '.json')
            for item in items:
                records.append({
                    'source_file': filename,
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
