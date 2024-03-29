# coding: utf-8

"""
A custom FileBrowseField.
"""

from django.db import models
from django import forms
from django.forms.widgets import Input
from django.db.models.fields import Field, CharField
from django.utils.safestring import mark_safe
from django.forms.util import flatatt
from django.utils.encoding import StrAndUnicode, force_unicode, smart_unicode, smart_str
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.forms.fields import EMPTY_VALUES
from django.conf import settings

import os
import re

from filebrowser.functions import _get_file_type, _url_join
from filebrowser.fb_settings import *

class FileBrowseFormField(forms.Field):
    default_error_messages = {
        'max_length': _(u'Ensure this value has at most %(max)d characters (it has %(length)d).'),
        'min_length': _(u'Ensure this value has at least %(min)d characters (it has %(length)d).'),
        'extension': _(u'Extension %(ext)s is not allowed. Only %(allowed)s is allowed.'),
    }
    
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        self.max_length, self.min_length = max_length, min_length
        self.initial_directory = kwargs['initial_directory']
        self.extensions_allowed = kwargs['extensions_allowed']
        del kwargs['initial_directory']
        del kwargs['extensions_allowed']
        super(FileBrowseFormField, self).__init__(*args, **kwargs)
    
    def clean(self, value):
        "Validates max_length and min_length. Returns a Unicode object. Validates extension ..."
        super(FileBrowseFormField, self).clean(value)
        if value in EMPTY_VALUES:
            return u''
        value = smart_unicode(value)
        value_length = len(value)
        if self.max_length is not None and value_length > self.max_length:
            raise forms.ValidationError(self.error_messages['max_length'] % {'max': self.max_length, 'length': value_length})
        if self.min_length is not None and value_length < self.min_length:
            raise forms.ValidationError(self.error_messages['min_length'] % {'min': self.min_length, 'length': value_length})
        file_extension = os.path.splitext(value)[1].lower()
        if self.extensions_allowed and not file_extension in self.extensions_allowed:
            raise forms.ValidationError(self.error_messages['extension'] % {'ext': file_extension, 'allowed': ", ".join(self.extensions_allowed)})
        return value
    

class FileBrowseWidget(Input):
    input_type = 'text'
    
    def __init__(self, attrs=None):
        self.initial_directory = attrs['initial_directory']
        self.extensions_allowed = attrs['extensions_allowed']
        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
    
    def render(self, name, value, attrs=None):
        #if value is None: value = ''
        if value is None:
            value = ''
        elif not isinstance(value, (str, unicode)):
            value = value.original
        final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
        init = final_attrs['initial_directory']
        final_attrs['initial_directory'] = _url_join(URL_ADMIN, init)
        if value != "":
            # Open filebrowser to same folder as currently selected media
            init = os.path.split(value)[0].replace(URL_WWW, "")
            if value[0] != '/':
                init = os.path.join(settings.MEDIA_ROOT, value).replace(PATH_SERVER, '')
                init = os.path.split(init)[0].lstrip('/')
                final_attrs['initial_directory'] = _url_join(URL_ADMIN, init)
            else:
                final_attrs['initial_directory'] = _url_join(URL_ADMIN, init)
        if value != '':
            # Only add the 'value' attribute if a value is non-empty.
            final_attrs['value'] = force_unicode(value)
            file = os.path.split(value)[1]
            if len(URL_WWW) < len(os.path.split(value)[0]):
                path = os.path.split(value)[0].replace(URL_WWW, "")
            else:
                path = ""
            file_type = _get_file_type(file)
            path_thumb = ""
            if file_type == 'Image':
                # check if thumbnail exists
                if os.path.isfile(os.path.join(PATH_SERVER, path, THUMB_PREFIX + file)):
                    path_thumb = os.path.join(os.path.split(value)[0], THUMB_PREFIX + file)
                else:
                    path_thumb = URL_FILEBROWSER_MEDIA + 'img/filebrowser_type_image.gif'
            elif file_type == "Folder":
                path_thumb = URL_FILEBROWSER_MEDIA + 'img/filebrowser_type_folder.gif'
            else:
                # if file is not an image, display file-icon (which is linked to the file) instead
                path_thumb = URL_FILEBROWSER_MEDIA + 'img/filebrowser_type_' + file_type.lower() + '.gif'
            if path_thumb[0] != '/':
                path_thumb = os.path.join(settings.MEDIA_URL, path_thumb)
            final_attrs['thumbnail'] = path_thumb
        path_search_icon = URL_FILEBROWSER_MEDIA + 'img/filebrowser_icon_show.gif'
        final_attrs['search_icon'] = path_search_icon
        return render_to_string("filebrowser/custom_field.html", locals())
    

class FileBrowserImageSize(object):
    
    def __init__(self, image_type, original):
        self.image_type = image_type
        self.original = original
        
    def __unicode__(self):
        return u'%s' % (self._get_image())
        
    def _get_image(self):
        if not hasattr(self, '_image_cache'):
            self._image_cache = self._get_image_name()
        return self._image_cache

    def _get_image_name(self):
        arg = self.image_type
        value = self.original
        value_re = re.compile(r'^(%s)' % (URL_WWW))
        value_path = value_re.sub('', value)
        filename = os.path.split(value_path)[1]
        if CHECK_EXISTS:
            path = os.path.split(value_path)[0]
            if os.path.isfile(os.path.join(PATH_SERVER, path, filename.replace(".", "_").lower() + IMAGE_GENERATOR_DIRECTORY, arg + filename)):
                img_value = '/'.join(os.path.split(value)[0], filename.replace(".", "_").lower() + IMAGE_GENERATOR_DIRECTORY, arg + filename)
                return u'%s' % (img_value)
            else:
                return u''
        else:
            img_value = '/'.join(os.path.split(value)[0], filename.replace(".", "_").lower() + IMAGE_GENERATOR_DIRECTORY, arg + filename)
            return u'%s' % (img_value)
        

class FileBrowserImageType(object):
    
    def __init__(self, original, image_list):
        for image_type in image_list:
            setattr(self, image_type[0].rstrip('_'), FileBrowserImageSize(image_type[0], original))
        

class FileBrowserFile(object):
    
    def __init__(self, value):
        self.original = value
        self._add_image_types()
    
    def _add_image_types(self):
        all_prefixes = []
        for imgtype in IMAGE_GENERATOR_LANDSCAPE:
            if imgtype[0] not in all_prefixes:
                all_prefixes.append(imgtype[0])
                setattr(self, imgtype[0].rstrip('_'), FileBrowserImageSize(imgtype[0], self.original))
        for imgtype in IMAGE_GENERATOR_PORTRAIT:
            if imgtype[0] not in all_prefixes:
                all_prefixes.append(imgtype[0])
                setattr(self, imgtype[0].rstrip('_'), FileBrowserImageSize(imgtype[0], self.original))
    
    def __unicode__(self):
        return self.original
    
    def crop(self):
        if not hasattr(self, '_crop_cache'):
            self._crop_cache = FileBrowserImageType(self.original, IMAGE_CROP_GENERATOR)
        return self._crop_cache


class FileBrowseField(Field):
    __metaclass__ = models.SubfieldBase
    
    def to_python(self, value):
        if isinstance(value, FileBrowserFile):
            return value
        return FileBrowserFile(value)
    
    def get_db_prep_value(self, value):
        return value.original
    
    def get_manipulator_field_objs(self):
        return [oldforms.TextField]
    
    def get_internal_type(self):
        return "CharField"
    
    def formfield(self, **kwargs):
        attrs = {}
        attrs["initial_directory"] = self.initial_directory
        attrs["extensions_allowed"] = self.extensions_allowed
        defaults = {'max_length': self.max_length}
        defaults['form_class'] = FileBrowseFormField
        defaults['widget'] = FileBrowseWidget(attrs=attrs)
        kwargs['initial_directory'] = self.initial_directory
        kwargs['extensions_allowed'] = self.extensions_allowed
        defaults.update(kwargs)
        return super(FileBrowseField, self).formfield(**defaults)
    
    def __init__(self, *args, **kwargs):
        try:
            self.initial_directory = kwargs['initial_directory']
            del kwargs['initial_directory']
        except:
            self.initial_directory = "/"
        try:
            self.extensions_allowed = kwargs['extensions_allowed']
            del kwargs['extensions_allowed']
        except:
            self.extensions_allowed = ""
        return super(FileBrowseField, self).__init__(*args, **kwargs)
    

