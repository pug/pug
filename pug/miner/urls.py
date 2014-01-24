from django.conf.urls import patterns, url
from django.conf import settings
#from django.views.generic import TemplateView
import django.views.static


from pug.miner.views import connections, home #StaticView

urlpatterns = patterns('',
    url(r'^$', home, name='home'),
    url(r'^(?:chart/)?(?:[Cc]onnect(?:ion)?s?|[Gg]raph)/(?P<edges>[^/]*)', connections),
    url(r'^static/(?P<path>.*)$', django.views.static.serve, { 'document_root': settings.STATIC_ROOT} ),
    url(r'^media/(?P<path>.*)$', django.views.static.serve, { 'document_root': settings.MEDIA_ROOT} ),
    #url(r'^(?P<page>.+)\.html$', StaticView.as_view()),
)
