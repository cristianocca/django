import datetime
import os
import warnings

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.db.models import FileField
from django.test import SimpleTestCase
from django.utils.encoding import force_str, force_text


class AWSS3Storage(Storage):
    """
    Simulate an AWS S3 storage which uses Unix-like paths and allows any
    characters in file names but where there aren't actual folders but just
    keys.
    """
    prefix = 'mys3folder/'

    # This one is important to test that Storage.save() doesn't replace '\' with
    # '/' (rather FileSystemStorage.save() does).
    def _save(self, name, content):
        return name

    def get_valid_name(self, name):
        return name

    def get_available_name(self, name, max_length=None):
        return name

    def generate_filename(self, filename, instance, upload_to):
        """
        This is the method that's important to override when using S3 so that
        os.path() isn't called, which would break S3 keys.
        """
        if callable(upload_to):
            return self.prefix + self.get_valid_name(upload_to(instance, filename))
        else:
            return (
                self.prefix +
                force_text(datetime.datetime.now().strftime(force_str(upload_to))) +
                self.get_valid_name(filename)
            )


class GenerateFilenameStorageTests(SimpleTestCase):

    def test_filefield_get_directory_deprecation(self):
        with warnings.catch_warnings(record=True) as warns:
            warnings.simplefilter('always')
            f = FileField(upload_to='some/folder/')
            self.assertEqual(f.get_directory_name(), os.path.normpath('some/folder/'))

        self.assertEqual(len(warns), 1)
        self.assertEqual(
            warns[0].message.args[0],
            'FileField now delegates file name and folder processing to the '
            'storage. get_directory_name() will be removed in Django 2.0.'
        )

    def test_filefield_get_filename_deprecation(self):
        with warnings.catch_warnings(record=True) as warns:
            warnings.simplefilter('always')
            f = FileField(upload_to='some/folder/')
            self.assertEqual(f.get_filename('some/folder/test.txt'), 'test.txt')

        self.assertEqual(len(warns), 1)
        self.assertEqual(
            warns[0].message.args[0],
            'FileField now delegates file name and folder processing to the '
            'storage. get_filename() will be removed in Django 2.0.'
        )

    def test_filefield_generate_filename(self):
        f = FileField(upload_to='some/folder/')
        self.assertEqual(
            f.generate_filename(None, 'test with space.txt'),
            os.path.normpath('some/folder/test_with_space.txt')
        )

    def test_filefield_generate_filename_with_upload_to(self):
        def upload_to(instance, filename):
            return 'some/folder/' + filename

        f = FileField(upload_to=upload_to)
        self.assertEqual(
            f.generate_filename(None, 'test with space.txt'),
            os.path.normpath('some/folder/test_with_space.txt')
        )

    def test_filefield_awss3_storage(self):
        """
        Simulate a FileField with an S3 storage which uses keys rather than
        folders and names. The key shouldn't break due to os.path() calls in
        FileField or Storage.
        """
        storage = AWSS3Storage()
        folder = 'not/a/folder/'

        f = FileField(upload_to=folder, storage=storage)
        key = 'my-file-key\\with odd characters'
        data = ContentFile('test')

        # Simulate call to f.save()
        resultKey = f.generate_filename(None, key)
        self.assertEqual(resultKey, AWSS3Storage.prefix + folder + key)

        resultKey = storage.save(resultKey, data)
        self.assertEqual(resultKey, AWSS3Storage.prefix + folder + key)

        # Repeat test with a callable.
        def upload_to(instance, filename):
            # Return a non-normalized path on purpose.
            return folder + filename

        f = FileField(upload_to=upload_to, storage=storage)

        # Simulate call to f.save()
        resultKey = f.generate_filename(None, key)
        self.assertEqual(resultKey, AWSS3Storage.prefix + folder + key)

        resultKey = storage.save(resultKey, data)
        self.assertEqual(resultKey, AWSS3Storage.prefix + folder + key)
