import os

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile


class HealthRecordFlowTests(TestCase):
    def tearDown(self):
        # Чистим за собой файлы, созданные во время тестов.
        for name in os.listdir(settings.DATA_JSON_DIR):
            if name != '.gitkeep':
                os.remove(settings.DATA_JSON_DIR / name)

    VALID_PAYLOAD = {
        'patient_full_name': 'Мария Петрова',
        'birth_date': '1988-03-15',
        'blood_type': 'O+',
        'height_cm': 165,
        'weight_kg': 60.5,
        'systolic_bp': 120,
        'diastolic_bp': 80,
        'heart_rate': 72,
        'temperature_c': 36.6,
        'measurement_date': '2024-01-10',
        'symptoms': 'Лёгкая усталость',
    }

    def test_view_data_shows_message_when_no_files(self):
        response = self.client.get(reverse('records:view_data'))
        self.assertContains(response, 'нет ни одного файла')

    def test_create_record_saves_json_file(self):
        response = self.client.post(reverse('records:create'), self.VALID_PAYLOAD, follow=True)
        self.assertEqual(response.status_code, 200)
        files = [f for f in os.listdir(settings.DATA_JSON_DIR) if f != '.gitkeep']
        self.assertEqual(len(files), 1)

    def test_create_record_rejects_systolic_not_greater_than_diastolic(self):
        payload = dict(self.VALID_PAYLOAD)
        payload['systolic_bp'] = 80
        payload['diastolic_bp'] = 80
        response = self.client.post(reverse('records:create'), payload)
        self.assertContains(response, 'должно быть больше нижнего')
        files = [f for f in os.listdir(settings.DATA_JSON_DIR) if f != '.gitkeep']
        self.assertEqual(len(files), 0)

    def test_create_record_rejects_invalid_blood_type(self):
        payload = dict(self.VALID_PAYLOAD)
        payload['blood_type'] = 'Z+'  # такой группы крови не существует
        response = self.client.post(reverse('records:create'), payload)
        self.assertEqual(response.status_code, 200)  # форма вернулась с ошибкой
        files = [f for f in os.listdir(settings.DATA_JSON_DIR) if f != '.gitkeep']
        self.assertEqual(len(files), 0)

    def test_upload_valid_json_is_saved_with_generated_name(self):
        content = (
            b'{"records": [{"patient_full_name": "Ivan Sidorov", "birth_date": "1990-01-01", '
            b'"blood_type": "A+", "height_cm": 180, "weight_kg": 80, "systolic_bp": 120, '
            b'"diastolic_bp": 80, "heart_rate": 70, "temperature_c": 36.6, '
            b'"measurement_date": "2024-01-01", "symptoms": []}]}'
        )
        upload = SimpleUploadedFile('../../evil.json', content, content_type='application/json')
        response = self.client.post(reverse('records:upload'), {'data_file': upload}, follow=True)
        self.assertEqual(response.status_code, 200)
        files = [f for f in os.listdir(settings.DATA_JSON_DIR) if f != '.gitkeep']
        self.assertEqual(len(files), 1)
        # имя файла НЕ должно совпадать с исходным и не должно содержать "../"
        self.assertNotIn('evil', files[0])
        self.assertNotIn('..', files[0])

    def test_upload_invalid_json_is_deleted(self):
        content = b'{"this is": "not valid record data"'  # намеренно битый JSON
        upload = SimpleUploadedFile('broken.json', content, content_type='application/json')
        response = self.client.post(reverse('records:upload'), {'data_file': upload}, follow=True)
        self.assertContains(response, 'не прошёл проверку и был удалён')
        files = [f for f in os.listdir(settings.DATA_JSON_DIR) if f != '.gitkeep']
        self.assertEqual(len(files), 0)

    def test_upload_wrong_extension_rejected(self):
        upload = SimpleUploadedFile('data.txt', b'hello', content_type='text/plain')
        response = self.client.post(reverse('records:upload'), {'data_file': upload})
        self.assertContains(response, 'Разрешены только файлы')
