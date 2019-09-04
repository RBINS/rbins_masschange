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
    columns = catalog._catalog.schema.keys()
    new_catalog_values = [
        ('ZContributors', 'ZCTextIndex', Extra),
        ('Contributors',  'KeywordIndex', None),
        ('OpenClose',  'FieldIndex', None),
    ]
    for k, tp, extra in new_catalog_values:
        if k not in catalog.Indexes:
            l.info('Creating %s index in catalog' % k)
            catalog.addIndex(k, tp, extra)
            catalog.reindexIndex(k, portal.REQUEST)

    reindex = True
    for k, _, _ in new_catalog_values:
        if k not in columns:
            l.info('Creating %s column in catalog' % k)
            catalog.addColumn(k)
            reindex = True

    if reindex:
        l.info('Reindexing')
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
                l.info('Done %s/%s (%s%s)' % (i, lb, cur, '%'))
                transaction.commit()
            b.getObject().reindexObject()
    transaction.commit()
# vim:set et sts=4 ts=4 tw=80:
