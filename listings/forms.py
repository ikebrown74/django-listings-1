# -*- coding: utf-8 -*-

from django import forms
from listings.models import Job, Type, JobStat
from categories.models import Category
from django.utils.safestring import mark_safe
from listings.conf import settings as listings_settings
from django.utils.translation import ugettext_lazy as _
from datetime import datetime, timedelta


class HorizRadioRenderer(forms.RadioSelect.renderer):
    """ this overrides widget method to put radio buttons horizontally
        instead of vertically.
    """
    def render(self):
        """Outputs radios"""
        return mark_safe(u'\n'.join([u'%s\n' % w for w in self]))


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ('category', 'jobtype', 'title', 'description', 'company', \
        'city', 'outside_location', 'url', 'poster_email', 'apply_online')
        widgets = {
            'jobtype': forms.RadioSelect(renderer=HorizRadioRenderer),
            'title': forms.TextInput(attrs={'size': 50}),
            'description': forms.Textarea(attrs={'rows': 15, 'cols': 80}),
            'city': forms.Select(attrs={'id': 'city_id'}),
            'outside_location': forms.TextInput(attrs={'id': 'location_outside_ro_where', \
             'maxlength': 140, 'size': 50}),
            'company': forms.TextInput(attrs={'size': 40}),
            'url': forms.TextInput(attrs={'size': 35}),
            'poster_email': forms.TextInput(attrs={'size': 40}),
        }

    def __init__(self, *args, **kwargs):
        super(JobForm, self).__init__(*args, **kwargs)
        self.fields['jobtype'].empty_label = None
        self.fields['category'].empty_label = None
        city = self.fields['city']
        choices = [(city.pk, unicode(city.name)) for city in city.queryset.all()]
        self.fields['city'].choices = choices

        try:
            self.fields['category'].initial = Category.on_site.all()[0].id
        except IndexError:
            pass
        try:
            self.fields['jobtype'].initial = Type.on_site.all()[0].id
        except IndexError:
            pass


class CaptchaJobForm(JobForm):
    if listings_settings.LISTINGS_CAPTCHA_POST == "simple":
        from captcha.fields import CaptchaField
        captcha = CaptchaField()
    else:
        pass


class ApplicationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.applicant_data = kwargs.pop('applicant_data')
        super(ApplicationForm, self).__init__(*args, **kwargs)
    apply_name = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'id': 'apply_name', 'size': 30}))
    apply_email = forms.EmailField(max_length=50, widget=forms.TextInput(attrs={'id': 'apply_email', 'size': 30}))
    apply_msg = forms.CharField(widget=forms.Textarea(attrs={'rows': 15, 'cols': 60, 'id': 'apply_msg'}))
    apply_cv = forms.FileField(required=False)

    if listings_settings.LISTINGS_CAPTCHA_APPLICATION == "simple":
        from captcha.fields import CaptchaField
        captcha = CaptchaField()

    def clean(self):
        cleaned_data = self.cleaned_data
        ip = self.applicant_data['ip']
        mb = self.applicant_data['mb']
        previous_applications = JobStat.objects.filter(created_on__range=mb, ip=ip, stat_type='A')
        m = previous_applications.count()
        if m > 0:
            #Getting how many minutes until user can apply again
            d1 = previous_applications.latest('created_on').created_on + timedelta(minutes=listings_settings.LISTINGS_MINUTES_BETWEEN)
            d2 = datetime.now()
            remaining = d1 - d2
            remaining = remaining.seconds / 60
            raise forms.ValidationError(_('You need to wait %(remaining)s more minute(s) before you can apply for a job again.') % {'remaining': remaining + 1})

        if cleaned_data['apply_cv']:
            #checking if cv extension is permitted
            extension = cleaned_data['apply_cv'].name.lower().split('.')[-1]
            if extension not in listings_settings.LISTINGS_CV_EXTENSIONS:
                raise forms.ValidationError(_('Your resume/CV has an invalid extension.'))
            #checking cv size does not exceed the permitted one
            permitted_size = listings_settings.LISTINGS_MAX_UPLOAD_SIZE
            if cleaned_data['apply_cv']._size > permitted_size:
                raise forms.ValidationError(_('Your resume/CV must not exceed the file size limit. (%(size)sMB)') % {'size': (permitted_size / 1024) / 1024})

        return cleaned_data
