#!/usr/bin/env python
# -*- coding: utf-8 -*-
import traceback
from plone.uuid.interfaces import IUUID
from Products.CMFCore.utils import getToolByName
import zope.schema
from zope import component, interface
from zope.component import adapter
from zope.interface import implementer
from zope.intid.interfaces import IIntIds
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile as FiveViewPageTemplateFile
import logging

from zope.schema.vocabulary import SimpleVocabulary
from zope.schema.vocabulary import SimpleTerm

import z3c.form
from z3c.form.util import getSpecification
from z3c.form.widget import FieldWidget
from z3c.relationfield import RelationValue
from z3c.form.interfaces import IFieldWidget

from zope.interface import invariant, Invalid
import plone.app.z3cform
import plone.z3cform.templates
from z3c.form.interfaces import ActionExecutionError, WidgetActionExecutionError
from plone.app.dexterity.behaviors.metadata import IOwnership
from plone.app.dexterity.behaviors.exclfromnav import IExcludeFromNavigation
from plone.app.dexterity.behaviors.discussion import IAllowDiscussion
from plone.autoform.form import AutoExtensibleForm
from plone.app.relationfield.behavior import IRelatedItems as BIRelatedItems
from collective.z3cform.keywordwidget.widget import (
    KeywordFieldWidget,
    InAndOutKeywordFieldWidget,
    InAndOutKeywordWidget)
from collective.z3cform.keywordwidget.field import Keywords

from z3c.relationfield.schema import RelationList, Relation, RelationChoice

from plone.autoform import directives
from z3c.form.browser.radio import RadioFieldWidget
from zope.i18nmessageid import MessageFactory
from z3c.form.interfaces import IFormLayer


from plone.app.z3cform.interfaces import IPloneFormLayer
from z3c.form.browser import textarea

try:
    from plone.app.widgets.interfaces import IWidgetsLayer
    from plone.app.widgets.dx import (RelatedItemsFieldWidget,
                                      AjaxSelectWidget,
                                      RelatedItemsWidget)
    HAS_W = True
except ImportError:
    HAS_W = False
    from plone.formwidget.contenttree import ObjPathSourceBinder

_ = MessageFactory('rbins_masschange')
logger = logging.getLogger('rbins_masschange.masschange')

def make_terms(items):
    """ Create zope.schema terms for vocab from tuples """
    terms = [SimpleTerm(value=pair[0], token=pair[0], title=pair[1])
             for pair in items]
    return terms


output_type_vocab = SimpleVocabulary(
    make_terms([("list", "Patient list"),
                ("summary", "Summary")]))


@adapter(getSpecification(IOwnership['contributors']), IFormLayer)
@implementer(IFieldWidget)
def ContributorsFieldWidget(field, request):
    widget = FieldWidget(field, textarea.TextAreaWidget(field, request))
    return widget


class IMassChangeSchema(interface.Interface):
    """Define masschange form fields"""
    # directives.widget('local_keywords', InAndOutKeywordWidget)

    overwrite = zope.schema.Bool(
        title=u"Overwrite",
        required=False,
        default=False,
        description=u"Overwrite values")

    if not HAS_W:
        selected_obj_paths = RelationList(
            title=u"Objects to change tags",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                source=ObjPathSourceBinder()))

        handle_related = zope.schema.Bool(
            title=u"Handle related items",
            required=False,
            default=False)

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                source=ObjPathSourceBinder()))
    else:
        directives.widget('selected_obj_paths', RelatedItemsWidget)
        directives.widget('related_obj_paths', RelatedItemsWidget)

        selected_obj_paths = RelationList(
            title=u"Objects to change tags",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                vocabulary="plone.app.vocabularies.Catalog"))

        handle_related = zope.schema.Bool(
            title=u"Handle related items",
            required=False,
            default=False)

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                vocabulary="plone.app.vocabularies.Catalog"))

    directives.widget(exclude_from_nav=RadioFieldWidget)
    directives.widget(allow_discussion=RadioFieldWidget)
    exclude_from_nav = zope.schema.Bool(
        title=u"Exclude from naviguation",
        required=False,
        default=None,
        description=u"Exclude from naviguation")

    allow_discussion = zope.schema.Bool(
        title=u"Allow comments",
        required=False,
        default=None,
        description=u"Allow comments")

    handle_keywords = zope.schema.Bool(
        title=u"Handle keywords",
        required=False,
        default=False)

    local_keywords = zope.schema.List(
        title=u"Keywords from this folder",
        required=False,
        description=u"Keyword (local)",
        value_type=zope.schema.Choice(
            vocabulary='rbins_masschange.localKeywords'))

    keywords = Keywords(
        title=u"keywords",
        description=u"Keyword (general)",
        required=False,
        index_name='Subject')

    manual_keywords = zope.schema.List(
        title=u"Keywords to add", required=False,
        value_type=(zope.schema.TextLine()))

    handle_contributors = zope.schema.Bool(
        title=u"Handle contributors",
        required=False,
        default=False)

    contributors = zope.schema.Text(
        title=u"contributors",
        description=u"Contributors (one per line)",
        required=False)

    handle_rights = zope.schema.Bool(
        title=u"Handle rights",
        required=False,
        default=False)

    rights = zope.schema.Text(
        title=u"rights",
        description=u"Rights",
        required=False)

#if HAS_W:
#    @adapter(getSpecification(IMassChangeSchema['contributors']), IFormLayer)
#    @implementer(IFieldWidget)
#    def ContributorsFieldWidget(field, request):
#        widget = FieldWidget(field, AjaxSelectWidget(request))
#        widget.vocabulary = 'plone.app.vocabularies.Users'
#        return widget
#    component.provideAdapter(ContributorsFieldWidget)


def default_keywords(self):
    return self.view.old_keywords[:]


class MassChangeForm(AutoExtensibleForm, z3c.form.form.Form):
    """ A form to output a HTML masschange from chosen parameters """
    schema = IMassChangeSchema
    ignoreContext = True

    def update(self):
        self.old_keywords = []
        try:
            self.old_keywords = [a for a in self.context.Subject()]
        except:
            pass
        psson = 'paths'
        sson = 'selected_obj_paths'
        obs = []
        pssonvalues = self.request.form.get(psson, [])
        ssonvalues = self.request.form.get(sson, [])
        tp = self.request.form.get('orig_template', '')
        # coming from folder_contents with filters and collections
        if (
            tp in ['folder_contents'] and
            isinstance(pssonvalues, list) and pssonvalues and
            isinstance(ssonvalues, list) and ssonvalues
        ):
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except:
                        pass
        else:
            # coming from folder_contents with filters
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except:
                        pass
            # coming from other cases
            elif sson in self.request.form:
                for item in self.request.form[sson]:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except:
                        pass
        ret = super(MassChangeForm, self).update()
        if obs:
            if HAS_W:
                portal = getToolByName(self.context,
                                       'portal_url').getPortalObject()
                uids = []
                for i in obs:
                    try:
                        uids.append(IUUID(portal.restrictedTraverse(i)))
                    except Exception:
                        continue
                obs = self.widgets[sson].separator.join(uids)
            self.request.form[u'form.widgets.%s' % sson] = obs
            self.widgets[sson].update()
        return ret

    @z3c.form.button.buttonAndHandler(_(u'Make Changes'), name='masschange')
    def masschange(self, action):
        # already passed (updateWidget called twice
        if self.status != '':
            return
        data, errors = self.extractData()
        if errors:
            self.status = "Please correct errors"
            return
        keywords = []
        for k in 'keywords', 'local_keywords', 'manual_keywords':
            d = data.get(k, None)
            if d:
                [keywords.append(i)
                 for i in d
                 if i not in keywords]
        keywords.sort()
        self.logs, ilogs = [], []

        ctbrs = data['contributors']
        if isinstance(ctbrs, basestring):
            ctbrs = [a.strip() for a in ctbrs.splitlines() if a.strip()]
        if isinstance(ctbrs, (list, tuple)):
            ctbrs = [a for a in ctbrs if a.strip()]

        rights = data['rights']
        if isinstance(rights, basestring) and rights.strip():
            rights = rights.strip()
        else:
            rights = None

        overwrite = data['overwrite']
        exclude_from_nav = data['exclude_from_nav']
        allow_discussion = data['allow_discussion']
        for item in data['selected_obj_paths']:
            changed = False
            if allow_discussion is not None:
                try:
                    ifc = IAllowDiscussion(item)
                    ifc.allow_discussion = allow_discussion
                    changed = True
                except (TypeError,) as exc:
                    # does not handle for now AT based content
                    # try at
                    try:
                        done = False
                        try:
                            item.allowDiscussion(allow_discussion)
                            done = True
                        except Exception:
                            pass
                        try:
                            item.editIsDiscussable(allow_discussion)
                            done = True
                        except Exception:
                            pass
                        if done:
                            item.reindexObject()
                            changed = True
                    except AttributeError:
                        pass
            if exclude_from_nav is not None:
                try:
                    ifc = IExcludeFromNavigation(item)
                    ifc.exclude_from_nav = exclude_from_nav
                    changed = True
                except (TypeError,) as exc:
                    # does not handle for now AT based content
                    # try at
                    try:
                        item.setExcludeFromNav(exclude_from_nav)
                        item.reindexObject()
                        changed = True
                    except AttributeError:
                        pass
            if (ctbrs or rights) and (data['handle_rights'] or
                                      data['handle_contributors']):
                try:
                    ownership = IOwnership(item)
                    if rights and data['handle_rights']:
                        ownership.rights = rights
                        changed = True
                    if ctbrs and data['handle_contributors']:
                        if ownership.contributors and not overwrite:
                            for i in ownership.contributors:
                                if i not in ctbrs:
                                    ctbrs.insert(0, i)
                        ownership.contributors = tuple(ctbrs)
                        changed = True
                except (TypeError,) as exc:
                    # does not handle for now AT based content
                    if ctbrs and data['handle_contributors']:
                        # try at
                        try:
                            if item.Contributors and not overwrite:
                                for i in item.Contributors:
                                    if i not in ctbrs:
                                        ctbrs.insert(0, i)
                            item.setContributors(tuple(ctbrs))
                            changed = True
                        except AttributeError:
                            pass
                    if rights and data['handle_rights']:
                        try:
                            item.Rights
                            item.setRights(rights)
                            changed = True
                        except AttributeError:
                            pass
            ppath = '/'.join(item.getPhysicalPath())
            if data['related_obj_paths'] and data['handle_related']:
                # item support related items
                related = []
                # archetypes
                try:
                    related = item.getRelatedItems()

                    def additem(xxx, related):
                        changed = False
                        xxx = [x for x in xxx if x not in related]
                        if xxx:
                            item.setRelatedItems(related + xxx)
                            changed = True
                        return changed
                except Exception:
                    additem = None
                # dexterity
                if not additem:
                    try:
                        related = BIRelatedItems(item).relatedItems

                        def additem(xxx, related):
                            changed = False
                            xxx = [x for x in xxx if x not in related]
                            if True or xxx:
                                intids = component.getUtility(IIntIds)
                                BIRelatedItems(item).relatedItems = (
                                    [RelationValue(intids.getId(obj))
                                     for obj in (related + xxx)])
                                #BIRelatedItems(item).relatedItems = (
                                #    [RelationValue(IUUID(obj))
                                #     for obj in (related + xxx)])
                                changed = True
                            return changed
                    except Exception:
                        additem = None
                if additem is not None:
                    changed = additem(data['related_obj_paths'], related)
            try:
                oldk = [a for a in self.context.Subject()]
            except:
                oldk = []
            oldk.sort()
            if (keywords != oldk) and data['handle_keywords']:
                try:
                    try:
                        if item.Subject() and not overwrite:
                            for val in item.Subject():
                                if val not in keywords:
                                    keywords.insert(0, val)
                        item.setSubject(keywords)
                        changed = True
                    except AttributeError:
                        if item.subject and not overwrite:
                            for val in item.subject:
                                if val not in keywords:
                                    keywords.insert(0, val)
                        item.subject = keywords
                        changed = True
                except Exception:
                    trace = traceback.format_exc()
                    msg = ('<li>%s %s: cant change keywords '
                           '<br/><pre>%s</pre>\n</li>') % (
                               ppath, keywords, trace)
                    logger.error(msg)
                    ilogs.append(msg)
            if changed:
                ilogs.append('<li>%s changed</li>\n' % ppath)
                item.reindexObject()
        if ilogs:
            ilogs.insert(0, u"<strong>MassChange complete</strong>")
            ilogs.insert(0, u"<ul>")
            ilogs.append('</ul>')
        self.logs.extend(ilogs)
        self.logs = '\n'.join(self.logs)


for k in ('keywords', 'local_keywords',):
    component.provideAdapter(
        z3c.form.widget.ComputedWidgetAttribute(
            default_keywords,
            field=IMassChangeSchema[k],
            view=MassChangeForm),
        name="default")


masschange_form_frame = plone.z3cform.layout.wrap_form(
    MassChangeForm,
    index=FiveViewPageTemplateFile("masschange.pt"))

# vim:set et sts=4 ts=4 tw=80:
