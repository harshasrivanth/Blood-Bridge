BloodBridge v0.6 prototype backend

Important:
- This version requires the provided fictional demo PDF before it can create a request or send donor email.
- Only searchable PDFs with the My Hospital demo markers are accepted. Scanned/image-only PDFs are not supported in this first v0.6 step.
- This marker check is a demo gate, NOT proof of genuine hospital issuance or medical validity.
- Never use the fictional sample for real medical care. Hospital/blood-bank staff must verify real requests and donor eligibility.

Deploy:
1. Copy backend files into your existing backend folder.
2. Keep your existing Render DATABASE_URL, GOOGLE_SCRIPT_URL, and GOOGLE_SCRIPT_SECRET environment variables.
3. Redeploy Render so requirements.txt installs python-multipart and pypdf.
4. Test using only the fictional sample PDF.
