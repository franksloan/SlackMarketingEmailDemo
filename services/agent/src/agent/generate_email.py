import base64
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.models.draft import ContentDraft

_ASSETS_DIR = Path(__file__).parents[4] / "assets"

def _load_logo() -> str:
    logo_path = _ASSETS_DIR / "aws-logo.png"
    with open(logo_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

_AWS_LOGO_B64 = _load_logo()


def _body_sections_to_html(body_sections) -> str:
    parts = []
    for section in body_sections:
        heading = getattr(section, "heading", None) or (section.get("heading", "") if isinstance(section, dict) else "")
        body = getattr(section, "body", None) or (section.get("body", "") if isinstance(section, dict) else "")
        if heading:
            parts.append(
                f'<div style="margin-top:20px; margin-bottom:6px; font-family:\'AmazonEmber\',Helvetica,arial,sans-serif; font-size:18px; line-height:26px; font-weight:bold; color:#161D26;">{heading}</div>'
            )
        if body:
            parts.append(
                f'<div style="margin-top:0; font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; color:#232B37;">{body}</div>'
            )
    return "\n".join(parts)


def render(draft: "ContentDraft", banner_image_b64: str | None = None, banner_image_filename: str | None = None) -> str:
    """Render a ContentDraft into the standard AWS marketing email HTML."""
    body_html = _body_sections_to_html(draft.body_sections)
    sign_off = draft.sign_off or "Best regards,<br>The AWS Team"

    if banner_image_b64:
        alt_text = banner_image_filename or "Campaign image"
        banner_html = (
            f'<img src="data:image/png;base64,{banner_image_b64}" width="600" alt="{alt_text}"'
            f' border="0" style="width:600px; border:0; border-radius:8px; display:block; margin:0 auto;">'
        )
    else:
        banner_html = (
            '<div style="width:600px; height:100px; border-radius:8px; mso-hide:all;'
            ' background:linear-gradient(135deg,#7C5AED 0%,#DF2A5D 50%,#FF9900 100%);"></div>'
        )

    secondary_modules = ""
    if draft.secondary_cta_text and draft.secondary_cta_url:
        secondary_modules = f"""
    <!-- MODULE: Secondary heading -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr>
          <td class="dark font-24" valign="top"
            style="font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-size:28px; line-height:36px; font-weight:bold; color:#161D26; text-align:left; mso-line-height-rule:exactly; padding:0 20px;">
            <div style="margin-top:10px; margin-bottom:10px;">{draft.subheadline}</div>
          </td>
        </tr>
        <tr><td height="16" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Secondary body -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr>
          <td class="dark" valign="top"
            style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; font-weight:normal; color:#232B37; text-align:left; mso-line-height-rule:exactly; padding:0 20px;">
            <div style="margin-top:0; margin-bottom:16px;">{draft.secondary_body}</div>
          </td>
        </tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Secondary CTA -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr>
          <td class="dark" valign="top"
            style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; font-weight:normal; color:#232B37; text-align:left; mso-line-height-rule:exactly; padding:0 20px;">
            <table align="left" cellpadding="0" cellspacing="0" border="0">
            <tbody><tr>
              <td class="btn-darkMode2"
                style="border-radius:40px; background-color:#ffffff; border:2px solid #161d26;" align="center">
                <a href="{draft.secondary_cta_url}" target="_blank"
                  style="text-decoration:none; color:#151d26; font-size:16px; font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-weight:bold; display:inline-block; border:2px solid #161D26; padding:12px 24px; border-radius:50px; line-height:20px; text-align:center;">
                  {draft.secondary_cta_text}
                </a>
              </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr><td height="40" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>"""

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <title>{draft.subject_line}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <meta content="width=device-width, minimal-ui, initial-scale=1.0, maximum-scale=1.0, user-scalable=0;" name="viewport">
  <meta content="telephone=no" name="format-detection">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark only">
  <!--[if gte mso 9]><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
  <!--[if mso]><style>body,table tr,table td,table th,a,span,table.MsoNormalTable{{font-family:Arial,Helvetica,sans-serif !important;}}</style><![endif]-->
  <style type="text/css">
    @media (prefers-color-scheme: dark) {{
      .btn-darkMode a {{ color: #fefefe !important; background-color: #161D26 !important; }}
      .btn-darkMode2 {{ border-color: #0972D3 !important; color: #0972D3 !important; }}
      .btn-darkMode2 a {{ color: #161D26 !important; }}
      .white {{ color: #ffffff !important; }}
      .dark {{ color: #232F3E !important; }}
      .dark2 {{ color: #888888 !important; }}
      .darkMode {{ background: #000000 !important; }}
      .lightMode {{ background: #fefefe !important; }}
      .lightMode1 {{ background-color: #fefefe !important; }}
      .nav-headerLinks td, .nav-headerLinks td a {{ color: #0972D3 !important; }}
    }}
    @media (prefers-color-scheme: dark) {{
      [data-ogsc] .btn-darkMode a {{ color: #161D26 !important; }}
      [data-ogsc] .btn-darkMode2 {{ border-color: #0972D3 !important; color: #0972D3 !important; }}
      [data-ogsc] .btn-darkMode2 a {{ color: #161D26 !important; }}
      [data-ogsc] .white {{ color: #ffffff !important; }}
      [data-ogsc] .darkMode {{ background: #000000 !important; }}
      [data-ogsc] .dark {{ color: #232F3E !important; }}
      [data-ogsc] .dark2 {{ color: #888888 !important; }}
      [data-ogsc] .lightMode {{ background: #fefefe !important; }}
      [data-ogsc] .lightMode1 {{ background-color: #fefefe !important; }}
    }}
    html {{ -webkit-text-size-adjust: none; }}
    body {{
      -webkit-font-smoothing: antialiased !important;
      -webkit-text-size-adjust: none !important;
      width: 100% !important;
      height: 100% !important;
      font-family: 'AmazonEmber', Helvetica, arial, sans-serif;
      margin-bottom: 0; padding-bottom: 0; margin-top: 0; margin-right: 0;
      margin-left: 0; padding-top: 0; padding-right: 0; padding-left: 0;
    }}
    body, table tr, table td, a, span, table.MsoNormalTable, th {{
      font-family: 'AmazonEmber', Arial, Helvetica, sans-serif;
    }}
    p, .undoreset div p, .undoreset p {{ margin-top: 14px; margin-bottom: 14px; }}
    a {{ outline: none !important; }}
    ul {{ margin-top: 0px !important; margin-bottom: 0px !important; padding-left: 30px !important; }}
    @media only screen and (max-width: 640px) {{
      .main {{ width: 100% !important; min-width: 100% !important; }}
      .deviceWidth1 {{ width: 90% !important; min-width: 90% !important; }}
      .deviceWidth2 {{ width: 80% !important; min-width: 80% !important; }}
      .block {{ display: block !important; margin: 0 auto !important; width: 100% !important; }}
      .center {{ text-align: center !important; }}
      .full-width img {{ width: 100% !important; height: auto !important; }}
      .font-24 {{ font-size: 24px !important; line-height: 30px !important; }}
    }}
  </style>
</head>
<body style="margin-bottom:0; -webkit-text-size-adjust:100%; padding-bottom:0; margin-top:0; margin-right:0; -ms-text-size-adjust:100%; margin-left:0; padding-top:0; padding-right:0; padding-left:0; width:100%;">

<table class="full-wrap" border="0" cellpadding="0" cellspacing="0" width="100%"
  style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; border-collapse:collapse; margin:0 auto;">
<tbody><tr>
<td class="darkMode" bgcolor="#ffffff" style="background-color:#ffffff;">

  <!-- Main 680px wrapper -->
  <table class="main mktoContainer" cellpadding="0" cellspacing="0" align="center" border="0" width="680"
    style="border-collapse:collapse; margin:0 auto; width:680px; min-width:680px;">
  <tbody>

    <!-- MODULE: Header / Logo -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="0" style="line-height:0px; font-size:0px;"></td></tr>
        <tr>
          <td valign="top" style="font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-size:28px; line-height:36px; font-weight:bold; color:#161D26; text-align:left; mso-line-height-rule:exactly;">
            <table class="main" width="600" cellpadding="0" cellspacing="0"
              style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
            <tbody><tr>
            <td valign="top" class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
              <table class="main" width="680" align="center" border="0" cellpadding="0" cellspacing="0"
                style="width:680px; margin:0 auto; border-spacing:0;">
              <tbody>
              <tr><td height="24" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
              <tr>
                <td align="center" style="text-align:center;">
                  <a href="https://aws.amazon.com/" target="_blank" style="text-decoration:none; color:#007eb9;">
                    <img src="data:image/png;base64,{_AWS_LOGO_B64}" width="75" border="0" alt="AWS Logo"
                      style="display:block; margin:0 auto;">
                  </a>
                </td>
              </tr>
              <tr><td height="24" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
              </tbody></table>
            </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr>
          <td class="lightMode" bgcolor="#ffffff" style="background-color:#ffffff;">
            <table width="100%" cellpadding="0" cellspacing="0"
              style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%; border-collapse:collapse;" border="0" class="deviceWidth1" align="center">
            <tbody><tr>
              <td class="full-width" valign="top" style="text-align:center;">
                {banner_html}
              </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr><td height="24" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        <tr><td height="16" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Title (headline) -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="0" style="line-height:0px; font-size:0px;"></td></tr>
        <tr>
          <td class="dark font-24" valign="top"
            style="font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-size:28px; line-height:36px; font-weight:bold; color:#161D26; text-align:left; mso-line-height-rule:exactly;">
            <table class="main" width="680" cellpadding="0" cellspacing="0"
              style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:680px;" border="0" align="center">
            <tbody><tr>
            <td class="lightMode" bgcolor="#ffffff" style="background-color:#ffffff;">
              <table class="deviceWidth1" width="600" align="center" border="0" cellpadding="0" cellspacing="0"
                style="width:600px; margin:0 auto; border-spacing:0;">
              <tbody>
              <tr>
                <td class="dark center font-24"
                  style="text-align:center; font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-size:36px; line-height:44px; color:#161D26; mso-line-height-rule:exactly; font-weight:bold;">
                  <div>{draft.headline}</div>
                </td>
              </tr>
              </tbody></table>
            </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr><td height="40" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Body text -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="0" style="line-height:0px; font-size:0px;"></td></tr>
        <tr>
          <td class="dark" valign="top"
            style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; font-weight:normal; color:#232B37; text-align:left; mso-line-height-rule:exactly;">
            <table class="main" width="680" cellpadding="0" cellspacing="0"
              style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:680px;" border="0" align="center">
            <tbody><tr>
            <td class="lightMode" bgcolor="#ffffff" style="background-color:#ffffff;">
              <table class="deviceWidth1" width="600" align="center" border="0" cellpadding="0" cellspacing="0"
                style="width:600px; margin:0 auto; border-spacing:0; padding:0 20px;">
              <tbody>
              <tr>
                <td style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; color:#232B37;">
                  {body_html}
                </td>
              </tr>
              </tbody></table>
            </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr><td height="40" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Primary CTA -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="0" style="line-height:0px; font-size:0px;"></td></tr>
        <tr>
          <td class="dark" valign="top"
            style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; font-weight:normal; color:#232B37; text-align:left; mso-line-height-rule:exactly; padding:0 20px;">
            <table align="left" cellpadding="0" cellspacing="0" border="0">
            <tbody><tr>
              <td class="btn-darkMode" style="border-radius:40px; background-color:#161d26;" align="center">
                <a href="{draft.primary_cta_url}" target="_blank"
                  style="text-decoration:none; color:#ffffff; font-size:16px; font-family:'AmazonEmber',Helvetica,arial,sans-serif; font-weight:bold; display:inline-block; border:2px solid #161D26; padding:12px 24px; border-radius:50px; line-height:20px; text-align:center;">
                  {draft.primary_cta_text}
                </a>
              </td>
            </tr></tbody></table>
          </td>
        </tr>
        <tr><td height="40" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>
    {secondary_modules}

    <!-- MODULE: Sign-off -->
    <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:100%;" border="0" align="center">
      <tbody><tr>
      <td class="lightMode" style="background-color:#ffffff;" bgcolor="#ffffff">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="0" style="line-height:0px; font-size:0px;"></td></tr>
        <tr>
          <td class="dark" valign="top"
            style="font-family:AmazonEmber,arial,Helvetica,sans-serif; font-size:16px; line-height:24px; font-weight:normal; color:#232B37; text-align:left; mso-line-height-rule:exactly; padding:0 20px;">
            <div>{sign_off}</div>
          </td>
        </tr>
        <tr><td height="40" style="line-height:1px; font-size:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

    <!-- MODULE: Footer -->
    <tr>
    <td>
      <table cellpadding="0" cellspacing="0" align="center" border="0" width="100%"
        style="margin:0 auto; min-width:100%;">
      <tbody><tr>
      <td class="lightMode" bgcolor="#ffffff" style="background-color:#ffffff;">
        <table class="deviceWidth1" width="600" cellpadding="0" cellspacing="0"
          style="border-spacing:0; mso-table-lspace:0pt; mso-table-rspace:0pt; margin:0 auto; width:600px;" border="0" align="center">
        <tbody>
        <tr><td height="16" style="font-size:1px; line-height:1px;">&nbsp;</td></tr>
        <tr>
          <td class="dark2"
            style="vertical-align:top; color:#888888; font-size:14px; line-height:20px; text-align:left; font-family:'AmazonEmber',arial,helvetica; font-weight:normal;">

            <!-- Nav links -->
            <table width="100%" cellspacing="0" cellpadding="0" border="0">
            <tbody><tr>
            <td style="padding:10px 0px; border-top:1px solid #e8e8e8;">
              <table style="border-collapse:collapse;" width="100%" cellspacing="0" cellpadding="0" border="0" align="center">
              <tbody><tr><td align="center">
                <table style="border-collapse:collapse;" width="100%" cellspacing="0" cellpadding="0" border="0" align="center">
                <tbody><tr>
                <td style="font-size:9px; color:#999999; line-height:16px;" align="center">
                  <a href="https://console.aws.amazon.com/" mktnotrack="true" style="color:#007eb9; text-decoration:none;" target="_blank"> My Account </a>|
                  <a href="https://aws.amazon.com/getting-started/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Getting Started</a> |
                  <a href="http://aws.amazon.com/products/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Products</a> |
                  <a href="http://aws.amazon.com/solutions/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Solutions</a> |
                  <a href="http://aws.amazon.com/pricing/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Pricing</a> |
                  <a href="https://aws.amazon.com/partners/work-with-partners/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Partners</a> |
                  <a href="http://aws.amazon.com/documentation-overview/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Documentation</a> |
                  <a href="http://aws.amazon.com/training/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Training</a> |
                  <a href="http://aws.amazon.com/about-aws/events/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Events &amp; Webinars</a> |
                  <a href="http://aws.amazon.com/activate/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> AWS Activate</a> |
                  <a href="https://aws.amazon.com/marketplace/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Marketplace</a> |
                  <a href="http://aws.amazon.com/new/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> What&#39;s New</a> |
                  <a href="http://aws.amazon.com/blogs/aws/?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=" style="color:#007eb9; text-decoration:none;" target="_blank"> Blog</a>
                </td>
                </tr></tbody></table>
              </td></tr></tbody></table>
            </td>
            </tr></tbody></table>

            <!-- Legal footer -->
            <table style="max-width:600px;" width="100%" cellspacing="0" cellpadding="0" border="0" align="center">
            <tbody><tr>
            <td style="font-size:12px; line-height:18px; color:#666666;" align="center">
              <dl>
                <dt style="color:#666666; font-size:10px; text-align:center;">
                  If you'd rather not receive future emails from Amazon Web Services,
                  <a href="https://pages.awscloud.com/communication-preferences.html?sc_channel=em&sc_campaign=&sc_publisher=aws&sc_medium=em_&sc_content=loc&sc_country=&sc_region=&param=unsubscribe&mkt_unsubscribe=1"
                    style="-ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; color:#007eb9; font-size:10px; text-decoration:none;" target="_blank">unsubscribe here</a>.
                </dt>
                <dt style="color:#666666; font-size:10px; text-align:center;">
                  Amazon Web Services, Inc. is a subsidiary of Amazon.com, Inc. Amazon.com is a registered trademark of Amazon.com.<br>
                </dt>
                <dt style="color:#666666; font-size:10px; text-align:center;">
                  This message was produced and distributed by Amazon Web Services, Inc. or its
                  <a href="https://aws.amazon.com/legal/marketingentities/"
                    style="-ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; color:#007eb9; font-size:10px; text-decoration:none;" target="_blank">affiliates</a>,
                  410 Terry Ave. North, Seattle, WA 98109.
                </dt>
                <dt style="color:#666666; font-size:10px; text-align:center;">
                  &copy;2025, Amazon Web Services, Inc. or its affiliates. All rights reserved.
                  Read our <a href="https://aws.amazon.com/privacy/"
                    style="-ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; color:#007eb9; font-size:10px; text-decoration:none;" target="_blank">Privacy Notice</a>.
                </dt>
              </dl>
            </td>
            </tr></tbody></table>

          </td>
        </tr>
        <tr><td height="20" style="font-size:1px; line-height:1px;">&nbsp;</td></tr>
        </tbody></table>
      </td>
      </tr></tbody></table>
    </td>
    </tr>

  </tbody>
  </table>
  <!-- /Main wrapper -->

</td>
</tr></tbody>
</table>

</body>
</html>
"""

