# -*- coding: utf-8 -*-

from django.db import models
from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_str, force_unicode
from django.utils.translation import ugettext_lazy as _
from django import VERSION as django_version
from django.contrib.sites.models import Site
from django.contrib.sites.managers import CurrentSiteManager
from django.conf import settings as django_settings

from listings.helpers import last_hour, getIP
from listings.models.base_models import Posting
from listings.conf import settings as listings_settings

import datetime
import uuid
import time

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

# class Category(SiteModel):
#     ''' The Category model, very straight forward. Includes a get_total_jobs
#         method that returns the total of jobs with that category.
#         The save() method is overriden so it can automatically asign
#         a category order in case no one is provided.
#     '''
#     name = models.CharField(_('Name'), unique=True, max_length=32, blank=False)
#     slug = models.SlugField(_('Slug'), unique=True, max_length=32, blank=False)
#     title = models.TextField(_('Title'), blank=True)
#     description = models.TextField(_('Description'), blank=True)
#     keywords = models.TextField(_('Keywords'), blank=True)
#     category_order = models.PositiveIntegerField(_('Category order'),
#                                                     unique=True, blank=True)

#     class Meta:
#         app_label = 'listings'
#         verbose_name = _('Category')
#         verbose_name_plural = _('Categories')

#     def get_total_jobs(self):
#         return Job.active.filter(category=self).count()

#     def __unicode__(self):
#         return self.name

#     @models.permalink
#     def get_absolute_url(self):
#         return ('listings_job_list_category', [self.slug])

#     def save(self, *args, **kwargs):
#         if not self.category_order:
#             try:
#                 self.category_order = Category.objects.\
#                                     latest('category_order').category_order + 1
#             except Category.DoesNotExist:
#                 self.category_order = 0
#         if not self.slug:
#             self.slug = slugify(self.name)
#         super(Category, self).save(*args, **kwargs)


class Type(models.Model):
    ''' The Type model, nothing special, just the name and
        slug fields. Again, the slug is slugified by the overriden
        save() method in case it's not provided.
    '''
    name = models.CharField(_('Name'), unique=True, max_length=16, blank=False)
    slug = models.SlugField(_('Slug'), unique=True, max_length=32, blank=False)
    sites = models.ManyToManyField(Site)
    objects = models.Manager()
    on_site = CurrentSiteManager()

    class Meta:
        app_label = 'listings'
        verbose_name = _('Type')
        verbose_name_plural = _('Types')

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(Type, self).save(*args, **kwargs)


# class City(SiteModel):
#     ''' A model for cities, with a get_total_jobs method to get
#         the total of jobs in that city, save() method is overriden
#         to slugify name to ascii_name.
#     '''
#     name = models.CharField(_('Name'), unique=True, max_length=50, blank=False)
#     ascii_name = models.SlugField(_('ASCII Name'), unique=True, max_length=50, blank=False)

#     class Meta:
#         app_label = 'listings'
#         verbose_name = _('City')
#         verbose_name_plural = _('Cities')

#     def get_total_jobs(self):
#         return Job.active.filter(city=self).count()

#     def __unicode__(self):
#         return self.name

#     def save(self, *args, **kwargs):
#         if not self.ascii_name:
#             self.ascii_name = slugify(self.name)
#         super(City, self).save(*args, **kwargs)


class Job(Posting):
    if django_version[:2] > (1, 2):
        category = models.ForeignKey('categories.Category', verbose_name=_('Category'), blank=False, null=True, on_delete=models.SET_NULL)
        jobtype = models.ForeignKey(Type, verbose_name=_('Job Type'), blank=False, null=True, on_delete=models.SET_NULL)
    else:
        category = models.ForeignKey('categories.Category', verbose_name=_('Category'), blank=False, null=False)
        jobtype = models.ForeignKey(Type, verbose_name=_('Job Type'), blank=False, null=False)

    company = models.CharField(_('Company'), max_length=150, blank=False)
    company_slug = models.SlugField(max_length=150,
                                            blank=False, editable=False)
    city = models.ForeignKey('cities_light.City', verbose_name=_('City'), null=True, blank=True)

    #url of the company
    url = models.URLField(verify_exists=False, max_length=150, blank=True)

    #url of the job post
    joburl = models.CharField(blank=True, editable=False, max_length=32)

    apply_online = models.BooleanField(default=True, verbose_name=_('Allow online applications.'),
                                    help_text=_('If you are unchecking this, then add a description on how to apply online!'))

    class Meta:
        app_label = 'listings'
        verbose_name = _('Job')
        verbose_name_plural = _('Jobs')

    def get_location(self):
        return self.city or self.outside_location
    get_location.admin_order = 'location'
    get_location.short_description = 'Location'

    def get_application_count(self):
        return JobStat.objects.filter(job=self, stat_type='A').count()

    def increment_view_count(self, request):  # TODO: Move to Posting
        lh = last_hour()
        ip = getIP(request)
        hits = JobStat.objects.filter(created_on__range=lh,
                                        ip=ip, stat_type='H', job=self).count()
        if hits < listings_settings.LISTINGS_MAX_VISITS_PER_HOUR:
            self.views_count = self.views_count + 1
            self.save()
            new_hit = JobStat(ip=ip, stat_type='H', job=self)
            new_hit.save()

    def clean(self):
        #making sure a job location is selected/typed in
        if self.city:
            self.outside_location = ''
        elif len(self.outside_location.strip()) > 0:
            self.city = None
        else:
            raise ValidationError(_('You must select or type a job location.'))

    def save(self, *args, **kwargs):
        #saving auth code
        if not self.auth:
            self.auth = md5(unicode(self.id) + \
                            unicode(uuid.uuid1()) + \
                            unicode(time.time())).hexdigest()
        #saving company slug
        self.company_slug = slugify(self.company)

        #saving job url
        self.joburl = slugify(self.title) + \
                        '-' + listings_settings.LISTINGS_AT_URL + \
                        '-' + slugify(self.company)

        #saving with textile
        if listings_settings.LISTINGS_MARKUP_LANGUAGE == 'textile':
            import textile
            self.description_html = mark_safe(
                                        force_unicode(
                                            textile.textile(
                                                smart_str(self.description))))
        #or markdown
        elif listings_settings.LISTINGS_MARKUP_LANGUAGE == 'markdown':
            import markdown
            self.description_html = mark_safe(
                                        force_unicode(
                                            markdown.markdown(
                                                smart_str(self.description))))
        else:
            self.description_html = self.description

        super(Job, self).save(*args, **kwargs)
        current_site = Site.objects.get(pk=django_settings.SITE_ID)
        if current_site not in self.sites.all():
            self.sites.add(current_site)


class JobStat(models.Model):
    APPLICATION = 'A'
    HIT = 'H'
    SPAM = 'S'
    STAT_TYPES = (
        (APPLICATION, _('Application')),
        (HIT, _('Hit')),
        (SPAM, _('Spam')),
    )
    if django_version[:2] > (1, 2):
        job = models.ForeignKey(Job, blank=False, null=True, on_delete=models.SET_NULL)
    else:
        job = models.ForeignKey(Job)
    created_on = models.DateTimeField(default=datetime.datetime.now())
    ip = models.IPAddressField()
    stat_type = models.CharField(max_length=1, choices=STAT_TYPES)
    description = models.CharField(_('Description'), max_length=250)
    sites = models.ManyToManyField(Site)
    objects = models.Manager()
    on_site = CurrentSiteManager()

    class Meta:
        app_label = 'listings'
        verbose_name = _('Job Stat')
        verbose_name_plural = _('Job Stats')

    def __unicode__(self):
        return self.description

    def save(self, *args, **kwargs):
        if self.stat_type == self.APPLICATION:
            self.description = u'Job application for [%d]%s from IP: %s' % \
                                            (self.job.pk, self.job.title, self.ip)
        elif self.stat_type == self.HIT:
            self.description = u'Visit for [%d]%s from IP: %s' % \
                                            (self.job.pk, self.job.title, self.ip)
        elif self.stat_type == self.SPAM:
            self.description = u'Spam report for [%d]%s from IP: %s' % \
                                            (self.job.pk, self.job.title, self.ip)
        else:
            self.description = u"Unkwown stat"
        super(JobStat, self).save(*args, **kwargs)


class JobSearch(models.Model):
    keywords = models.CharField(_('Keywords'), max_length=100, blank=False)
    created_on = models.DateTimeField(_('Created on'), default=datetime.datetime.now())

    class Meta:
        app_label = 'listings'
        verbose_name = _('Search')
        verbose_name_plural = _('Searches')

    def __unicode__(self):
        return self.keywords
