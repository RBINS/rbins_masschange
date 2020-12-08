#!/usr/bin/env python
# -*- coding: utf-8 -*-
from binascii import b2a_qp
from zope import interface, component
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm
from zope.schema.interfaces import IVocabularyFactory, IContextSourceBinder

from Products.CMFPlone.utils import safe_unicode, getToolByName
from zope.site.hooks import getSite

from plone.app.textfield.utils import getAllowedContentTypes
from plone.i18n.normalizer.base import baseNormalize

from rbins_masschange.utils import magicstring, infolder_keywords


def uniquify(t):
    s = []
    [s.append(i) for i in t if not i in s]
    return s


class LocalKeywordFactory(object):
    key = None
    interface.implements(IVocabularyFactory,)

    def __init__(self, key):
        self.key = key

    def __call__(self, context):
        assert self.key is not None
        if isinstance(context, dict):
            context = context.get('context', None)
        values = infolder_keywords(context, self.key)
        values = uniquify(
            [magicstring(a.strip()).decode('utf-8')
             for a in values])
        values.sort()
        values = [
            SimpleTerm(baseNormalize(category).strip(),
                       baseNormalize(category).strip(),
                       category) for category in uniquify(values)]
        return SimpleVocabulary(values)

LocalSubjectsVocabulary = LocalKeywordFactory('Subject')


class ContributorsVocabularyFactory(object):
    """
    """
    interface.implements(IVocabularyFactory)

    def __call__(self, context, query=None):
        site = getSite()
        self.catalog = getToolByName(site, "portal_catalog", None)
        if self.catalog is None:
            return SimpleVocabulary([])
        index = self.catalog._catalog.getIndex('Subject')

        def safe_encode(term):
            if isinstance(term, unicode):
                # no need to use portal encoding for transitional encoding from
                # unicode to ascii. utf-8 should be fine.
                term = term.encode('utf-8')
            return term

        # Vocabulary term tokens *must* be 7 bit values, titles *must* be
        # unicode
        items = [
            SimpleTerm(i, b2a_qp(safe_encode(i)), safe_unicode(i))
            for i in index._index
            if query is None or safe_encode(query) in safe_encode(i)
        ]
        return SimpleVocabulary(items)

ContributorsVocabulary = ContributorsVocabularyFactory()


class MimeTypesVocabularyFactory(object):
    """
    """
    interface.implements(IVocabularyFactory)

    def lookupMime(self, name):
        mimetypes = self.mimetool.lookup(name)
        if len(mimetypes):
            return mimetypes[0].name()
        else:
            return name

    def __call__(self, context, query=None):
        self.mimetool = getToolByName(context, 'mimetypes_registry')

        mimetypes = getAllowedContentTypes()
        terms = [SimpleTerm(value=mimetype, token=mimetype, title=self.lookupMime(mimetype))
                 for mimetype in mimetypes]
        return SimpleVocabulary(terms)

MimeTypesVocabulary = MimeTypesVocabularyFactory()
