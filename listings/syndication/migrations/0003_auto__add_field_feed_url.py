# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'Feed.url'
        db.add_column('syndication_feed', 'url',
                      self.gf('django.db.models.fields.CharField')(default='echo/', unique=True, max_length=100),
                      keep_default=False)


    def backwards(self, orm):
        # Deleting field 'Feed.url'
        db.delete_column('syndication_feed', 'url')


    models = {
        'sites.site': {
            'Meta': {'ordering': "('domain',)", 'object_name': 'Site', 'db_table': "'django_site'"},
            'domain': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'syndication.feed': {
            'Meta': {'object_name': 'Feed'},
            'feed_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['syndication.FeedType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'site': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['sites.Site']", 'symmetrical': 'False'}),
            'url': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
        },
        'syndication.feedtype': {
            'Meta': {'object_name': 'FeedType'},
            'content_type': ('django.db.models.fields.CharField', [], {'default': "'application/xml'", 'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'template': ('django.db.models.fields.files.FileField', [], {'max_length': '100'})
        }
    }

    complete_apps = ['syndication']