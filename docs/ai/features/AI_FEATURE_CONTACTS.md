# AI FEATURE: CONTACTS
The Contacts system manages an address book of people, organizations, and communication handles. It acts as the system's "Social Graph."

## 1. Storage Strategy (Hybrid Model)
The system implements a dual-layer storage approach to ensure both portability and local speed:
- **Primary (CardDAV):** If configured, the system syncs with a CardDAV server (e.g., Radicale, Nextcloud). This allows the address book to be shared across devices.
- **Fallback (Local):** If no CardDAV server is present, the system defaults to a local `data/contacts.json` file.

## 2. Technical Implementation
- **vCard Engine:** Implements a strict RFC 6350 compliant parser and builder. This handles the complexities of vCard formatting, including:
    - Proper escaping of special characters.
    - Support for group prefixes.
    - Multi-value properties (e.g., multiple phone numbers).
- **Contact Resolution:** A specialized utility to search for a contact by name and return the most likely email address or phone number for a given action (e.g., "Email John" $\rightarrow$ looks for `John` $\rightarrow$ returns `john@example.com`).

## 3. Data Import/Export
- **vCard (.vcf):** Direct import/export of industry-standard contact cards.
- **CSV:** Support for bulk importing contacts from spreadsheet formats.

## 4. AI Implementation Notes
When managing contacts, the AI should:
1.  **Resolve Ambiguity:** If multiple contacts share a name (e.g., "John Smith" and "John Doe"), ask the user for clarification before sending a message.
2.  **Update Metadata:** Suggest adding a contact if the user frequently interacts with an email address that isn't in the address book.
3.  **Sync Check:** If CardDAV is enabled, the AI can notify the user if local changes haven't synced.