# -*- coding: utf-8 -*-

from django.shortcuts import get_object_or_404, redirect, render_to_response

#  Deprecated generic views
from django.views.generic.list_detail import object_detail, object_list
from django.views.generic.create_update import update_object

#  Django 1.5 class base generic views
from django.views.generic import ListView
from django.views.generic.edit import FormView
from django.views.generic.detail import DetailView

from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _
from django.template import RequestContext
from django.db.models import Count
from django.http import Http404, HttpResponseRedirect

from listings.models import Job, Type, JobStat, JobSearch
from listings.models.base_models import POSTING_TEMPORARY, POSTING_ACTIVE
from listings.postman import *
from listings.helpers import *
from listings.forms import ApplicationForm
from listings.conf import settings as listings_settings
if listings_settings.LISTINGS_CAPTCHA_POST == 'simple':
    from listings.forms import CaptchaJobForm
    form_class = CaptchaJobForm
else:
    from listings.forms import JobForm
    form_class = JobForm

from categories.models import Category
from cities_light.models import City


class IndexAdView(ListView):
    queryset = Job.active.order_by('-created_on').select_related()
    template_name = 'listings/index.html'
    context_object_name = 'ad_list'
    paginate_by = listings_settings.LISTINGS_JOBS_PER_PAGE


class AdPostView(FormView):
    template_name = 'listings/ad_form.html'
    form_class = form_class

    def form_valid(self, form):
        ad = form.save()
        return HttpResponseRedirect(reverse('listings_job_verify', kwargs={'job_id': ad.pk, 'auth': ad.auth}))


class AdDetailView(DetailView):
    model = Job
    context_object_name = 'ad'

    def get_context_data(self, **kwargs):
        context = super(AdDetailView, self).get_context_data(**kwargs)
        context['application_form'] = self.request.session.pop('application_form', ApplicationForm())
        return context

    def get_object(self, queryset=None):
        #  ad.increment_view_count(request)
        return get_object_or_404(Job, pk=self.kwargs.get('pk'), ad_url=self.kwargs.get('ad_url'))


def ad_apply(request, job_id, ad_url):
    ad = get_object_or_404(Job, pk=job_id, ad_url=ad_url)
    if request.method == 'POST' and ad.apply_online and listings_settings.LISTINGS_APPLICATION_NOTIFICATIONS:
        ip = getIP(request)
        mb = minutes_between()

        form = ApplicationForm(request.POST,
                               request.FILES,
                               applicant_data={'ip': ip, 'mb': mb})

        if form.is_valid():
            application_mail = MailApplyOnline(ad, request)
            application_mail.start()

            #Save JobStat application
            ja = JobStat(job=ad, ip=ip, stat_type='A')
            ja.save()
            messages.add_message(request, messages.INFO, _('Your application was sent successfully.'))
        else:
            request.session['application_form'] = form

        return HttpResponseRedirect(reverse('listings_ad_detail', kwargs={'pk': ad.id, 'ad_url': ad.ad_url}))
    raise Http404


def job_detail(request, job_id, ad_url):
    ''' Displays an active job and its application form depending if
        the job has online applications or not. Handles the job applications
        and sends notifications emails.
    '''
    try:
        job = Job.active.get(pk=job_id, ad_url=ad_url)
        extra_context = {'page_type': 'detail', 'cv_extensions': listings_settings.LISTINGS_CV_EXTENSIONS}

        # Increment views
        job.increment_view_count(request)

        # Gets poster ip
        ip = getIP(request)

        # Only if the job has online applications ON and application
        # notifications are activated can the user apply online
        mb = minutes_between()
        if job.apply_online and listings_settings.LISTINGS_APPLICATION_NOTIFICATIONS:

            # Add CSRF protection
            extra_context.update(csrf(request))

            # If it's a job application
            if request.method == 'POST':

                # Gets the application
                form = ApplicationForm(request.POST,
                                       request.FILES,
                                       applicant_data={'ip': ip, 'mb': mb})

                # If the form is OK then send it to the job poster
                if form.is_valid():
                    application_mail = MailApplyOnline(job, request)
                    application_mail.start()

                    #Save JobStat application
                    ja = JobStat(job=job, ip=ip, stat_type='A')
                    ja.save()
                    messages.add_message(request, messages.INFO, _('Your application was sent successfully.'))
                    extra_context['page_type'] = 'application'
                    queryset = Job.active.filter(ad_url=ad_url)
                    return object_detail(request, queryset=queryset, object_id=job_id, extra_context=extra_context)
                else:
                    extra_context['form_error'] = True

            # Else create an empty application form
            else:
                form = ApplicationForm(applicant_data={'ip': ip, 'mb': mb})
            extra_context['apform'] = form
            extra_context['ad'] = job
            return render_to_response('listings/job_detail.html', extra_context, context_instance=RequestContext(request))

        # Only display the job, without an application form
        else:
            queryset = Job.active.filter(ad_url=ad_url)
            return object_detail(request, queryset=queryset, object_id=job_id, extra_context=extra_context, template_object_name='ad')

    # Instead of throwing a 404 error redirect to job unavailable page
    except Job.DoesNotExist:
        return redirect('listings_job_unavailable', permanent=True)


def job_verify(request, job_id, auth):
    ''' A view to display a newly created job.
    '''
    queryset = Job.objects.filter(auth=auth)
    # Setting page_type as 'verify' in order to
    # show edit and cancelation buttons in the template
    extra_context = {'page_type': 'verify'}
    return object_detail(request, queryset=queryset, object_id=job_id, extra_context=extra_context, template_object_name='ad', template_name='listings/job_verify.html')


def jobs_category(request, cslug=None, tslug=None):
    ''' Displays a job list by category and/or job type but
        those two are optional.
    '''
    extra_context = {}
    queryset = Job.active.all()
    if cslug:
        category = get_object_or_404(Category, slug=cslug)
        queryset = queryset.filter(category=category)
        extra_context['selected_category'] = category
    if tslug:
        jobtype = get_object_or_404(Type, slug=tslug)
        queryset = queryset.filter(jobtype=jobtype)
        extra_context['selected_jobtype'] = jobtype
    return object_list(request, queryset=queryset,
                    extra_context=extra_context,
                    paginate_by=listings_settings.LISTINGS_JOBS_PER_PAGE)


def jobs_in_city(request, city_name, tslug=None):
    ''' Display a job list by city and job type (optional).
    '''
    city = get_object_or_404(City, ascii_name=city_name)
    queryset = Job.active.filter(city=city)
    extra_context = {'city': city}
    if tslug:
        jobtype = get_object_or_404(Type, slug=tslug)
        queryset = queryset.filter(jobtype=jobtype)
        extra_context['selected_jobtype'] = jobtype
    return object_list(request, queryset=queryset,
                    extra_context=extra_context,
                    paginate_by=listings_settings.LISTINGS_JOBS_PER_PAGE)


def jobs_in_other_cities(request):
    ''' Displays a list with jobs in cities outside.
    '''
    queryset = Job.active.filter(city=None)
    return object_list(request, queryset=queryset)


def companies(request):
    ''' Displays the companies that have active jobs
        posted on the site.
    '''
    queryset = Job.active.values('company', 'company_slug') \
               .annotate(Count('company'))
    return object_list(request, queryset=queryset,
                                template_name='listings/company_list.html')


def jobs_at(request, company_slug, tslug=None):
    ''' Displays a job list by company, jobtype is optional.
    '''
    queryset = Job.active.filter(company_slug=company_slug)
    if tslug:
        jobtype = get_object_or_404(Type, slug=tslug)
        queryset = queryset.filter(jobtype=jobtype)
        extra_context['selected_jobtype'] = jobtype
    return object_list(request, queryset=queryset)


def job_confirm(request, job_id, auth):
    ''' A view to confirm a recently created job, if it has been published
        by a previously approved user then it gets automatically published,
        if not then it will need to be verified by a moderator.
    '''
    job = get_object_or_404(Job, pk=job_id, auth=auth)
    if job.status not in (POSTING_ACTIVE, POSTING_TEMPORARY):
        raise Http404
    new_post = job.is_temporary()
    requires_mod = not job.email_published_before() and \
                 listings_settings.LISTINGS_ENABLE_NEW_POST_MODERATION
    if requires_mod:
        messages.add_message(request,
                       messages.INFO,
                       _('Your job post needs to be verified by a moderator.'))
        if listings_settings.LISTINGS_POSTER_NOTIFICATIONS:
            pending_email = MailPublishPendingToUser(job, request)
            pending_email.start()
    else:
        messages.add_message(request,
                             messages.INFO,
                             _('Your job post has been published.'))
        if not job.is_active():
            job.activate()
        if new_post:
            if listings_settings.LISTINGS_POSTER_NOTIFICATIONS:
                publish_email = MailPublishToUser(job, request)
                publish_email.start()
    queryset = Job.objects.all()
    if listings_settings.LISTINGS_ADMIN_NOTIFICATIONS:
        admin_email = MailPublishToAdmin(job, request)
        admin_email.start()
    return object_detail(request, queryset=queryset, object_id=job_id, template_object_name='ad', template_name='listings/job_confirm.html')


def job_edit(request, job_id, auth):
    ''' A view for editing published or unpublished job posts.
    '''
    job = get_object_or_404(Job, pk=job_id, auth=auth)
    if job.status not in (POSTING_ACTIVE, POSTING_TEMPORARY):
        raise Http404
    return update_object(request, form_class=JobForm, object_id=job_id,
           post_save_redirect='../../../' +
           listings_settings.LISTINGS_VERIFY_URL + '/%(id)d/%(auth)s/')


def job_activate(request, job_id, auth):
    ''' Gets a job and activates it, only if it's not already activated,
        it also sends the notification mail to the poster.
    '''
    job = get_object_or_404(Job, pk=job_id, admin_auth=auth)
    extra_context = {}
    if not job.is_active():
        job.activate()
        if listings_settings.LISTINGS_POSTER_NOTIFICATIONS:
            publish_email = MailPublishToUser(job, request)
            publish_email.start()
        messages.add_message(request,
                             messages.INFO,
                             _('Your job has been activated.'))
        extra_context['page_type'] = 'activate'
    queryset = Job.active.all()
    return object_detail(request, queryset=queryset,
                            object_id=job_id, extra_context=extra_context)


def job_deactivate(request, job_id, auth):
    ''' Deactivates a job and shows an active jobs list.
    '''
    job = get_object_or_404(Job, pk=job_id, auth=auth)
    extra_context = {}
    if job.is_active() or job.is_temporary():
        job.deactivate()
        messages.add_message(request,
                             messages.INFO,
                             _('Your job has been deactivated.'))
        extra_context['page_type'] = 'deactivate'
    queryset = Job.active.all()
    return object_list(request, queryset=queryset,
                    extra_context=extra_context,
                    paginate_by=listings_settings.LISTINGS_JOBS_PER_PAGE)


def job_search(request):
    ''' A search view, does the job but not great. Job searches should be
        handled by a proper search app, namely django-haystack.
    '''
    query_string = ''
    found_entries = Job.objects.none()
    extra_context = {'keywords': ' '}
    if ('keywords' in request.POST) and request.POST['keywords'].strip():
        request.session['keywords'] = request.POST['keywords']
        query_string = request.session['keywords']
        extra_context['keywords'] = query_string
        search_fields = ['title', 'description', 'category',
                             'jobtype', 'city', 'outside_location', 'company', ]
        entry_query = get_query(query_string, search_fields)
        jobs_per_search = listings_settings.LISTINGS_JOBS_PER_SEARCH
        found_entries = Job.objects.filter(entry_query)\
                                     .order_by('-created_on')[:jobs_per_search]
        search = JobSearch(keywords=query_string)
        search.save()
    return object_list(request, queryset=found_entries,
                    extra_context=extra_context,
                    paginate_by=listings_settings.LISTINGS_JOBS_PER_PAGE)
