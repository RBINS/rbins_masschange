#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import transaction


class Extra:
    index_type = "Okapi BM25 Rank"
    lexicon_id = "plone_lexicon"


def setupVarious(context):
    """
    Miscellanous steps import handle.
    """
    l = logging.getLogger('rbins_masschange / setuphandler')
    if context.readDataFile('rbins_masschange_various.txt') is None:
        return

    portal = context.getSite()
    catalog = portal.portal_catalog

    for k, tp, extra in [
        ('ZContributors', 'ZCTextIndex', Extra),
        ('Contributors',  'KeywordIndex', None),
        ('OpenClose',  'FieldIndex', None),
    ]:
        if k not in catalog.Indexes:
            l.error('Creating %s in catalog' % k)
            catalog.addIndex(k, tp, extra)
            catalog.addColumn(k)
            catalog.reindexIndex(k, portal.REQUEST)

    columns = catalog._catalog.schema
    reindex = True
    for k in ('ZContributors', 'Contributors', 'OpenClose'):
        if k not in columns:
            l.warn('Creating %s in catalog' % k)
            catalog.addColumn(k)
            reindex = True

    if reindex:
        l.warn('Reindexing')
        # reindex documents
        brains = catalog.searchResults(**{})
        lb = len(brains)
        done = 0
        for i, b in enumerate(brains):
            cur = i * 100.0 / lb
            adone = int(cur) / 10
            if done != adone:
                # print each 10%
                done = adone
                l.warn('Done %s/%s (%s%s)' % (i, lb, cur, '%'))
                transaction.commit()
            b.getObject().reindexObject()
    transaction.commit()
# vim:set et sts=4 ts=4 tw=80:
