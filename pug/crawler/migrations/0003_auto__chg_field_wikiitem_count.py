# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):

        # Changing field 'WikiItem.count'
        db.alter_column(u'crawler_wikiitem', 'count', self.gf('django.db.models.fields.TextField')(null=True))

    def backwards(self, orm):

        # Changing field 'WikiItem.count'
        db.alter_column(u'crawler_wikiitem', 'count', self.gf('django.db.models.fields.IntegerField')(null=True))

    models = {
        u'crawler.wikiitem': {
            'Meta': {'object_name': 'WikiItem'},
            'abstract': ('django.db.models.fields.TextField', [], {'null': 'True'}),
            'count': ('django.db.models.fields.TextField', [], {'null': 'True'}),
            'crawled': ('django.db.models.fields.DateTimeField', [], {'unique': 'True', 'null': 'True'}),
            'crawler': ('django.db.models.fields.CharField', [], {'max_length': '30', 'null': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'modified': ('django.db.models.fields.DateTimeField', [], {'null': 'True'}),
            'text': ('django.db.models.fields.TextField', [], {'null': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '100', 'null': 'True'}),
            'toc': ('django.db.models.fields.TextField', [], {'null': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '256', 'unique': 'True', 'null': 'True'})
        }
    }

    complete_apps = ['crawler']