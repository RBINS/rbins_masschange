from Products.CMFCore.utils import getToolByName

PROFILE_ID = "profile-rbins_masschange:default"

def v3(context, logger=None):
    setup = getToolByName(context, 'portal_setup')
    setup.runImportStepFromProfile(PROFILE_ID, 'actions',
                                   run_dependencies=False)
    quickinstaller = getToolByName(context, 'portal_quickinstaller')
    if not quickinstaller.isProductInstalled('plone.formwidget.contenttree'):
        quickinstaller.installProduct('plone.formwidget.contenttree')

    if not quickinstaller.isProductInstalled('plone.formwidget.masterselect'):
        quickinstaller.installProduct('plone.formwidget.masterselect')

    if not quickinstaller.isProductInstalled('plone.formwidget.autocomplete'):
        quickinstaller.installProduct('plone.formwidget.autocomplete')
