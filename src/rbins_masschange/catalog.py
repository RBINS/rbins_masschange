#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import pkg_resources
import copy

from zope.component import adapts
from zope.interface import implements
from plone.indexer import indexer
from plone.dexterity.interfaces import IDexterityItem
from plone.app.dexterity.behaviors.metadata import IOwnership

from Products.Archetypes.interfaces.base import IBaseContent
from collective import dexteritytextindexer
from rbins_masschange.utils import magicstring
from eea.facetednavigation.browser.app.query import FacetedQueryHandler
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile



def _Contributors(item):
    try:
        ownership = IOwnership(item)
        ctbtrs = ownership.contributors
    except TypeError:
        try:
            ctbtrs = item.Contributors()
        except AttributeError:
            ctbtrs = []
    return [magicstring(a) for a in ctbtrs]


AContributors = indexer(IBaseContent)(_Contributors)
BContributors = indexer(IDexterityItem)(_Contributors)


def _ZContributors(item):
    return " ".join(_Contributors(item)).split()


AZContributors = indexer(IBaseContent)(_ZContributors)
BZContributors = indexer(IDexterityItem)(_ZContributors)


#class CFacetedQueryHandler(FacetedQueryHandler):
#    """Let a faceted view search on our shiny new zctindex"""
#
#    index = ViewPageTemplateFile(
#        pkg_resources.resource_filename(
#            'eea.facetednavigation', 'browser/template/query.pt')
#    )
#
#    def criteria(self, **kwargs):
#        query = super(CFacetedQueryHandler, self).criteria(**kwargs)
#        for k in [
#            'SearchableText',
#            'ZContributors',
#        ]:
#            if k in query:
#                searched_text = query[k]['query']
#                words = searched_text.strip().split()
#                globbed = ["{}*".format(word) for word in words]
#                query[k]['query'] = ' '.join(globbed)
#        query.pop('Language', None)
#        return query
# vim:set et sts=4 ts=4 tw=80:
