"""Pages publiques d'information légale, d'éthique et de confidentialité."""
from fastapi import APIRouter, Request

from ..conditions_legales import DATE_VERSION_CONDITIONS, VERSION_CONDITIONS
from ..templating import templates


router = APIRouter()


@router.get("/cadre-legal", name="cadre_legal")
@router.get("/conditions-utilisation", include_in_schema=False)
@router.get("/charte-ethique", include_in_schema=False)
@router.get("/confidentialite", include_in_schema=False)
@router.get("/mentions-legales", include_in_schema=False)
def cadre_legal(request: Request):
    return templates.TemplateResponse(
        request,
        "cadre_legal.html",
        {
            "version_conditions": VERSION_CONDITIONS,
            "date_version_conditions": DATE_VERSION_CONDITIONS,
        },
    )
