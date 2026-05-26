# code/main.py
# Dependencies: pip install openai
# Usage: python main.py

from __future__ import annotations
import hashlib
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Example:
    """A single fine-tuning example: system prompt + user input + ideal response."""
    system: str
    user: str
    assistant: str
    metadata: dict = field(default_factory=dict)

    def to_messages(self) -> dict:
        """Convert to the JSONL fine-tuning format."""
        return {
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
                {"role": "assistant", "content": self.assistant},
            ]
        }

    def fingerprint(self) -> str:
        """Hash of user + assistant content for deduplication."""
        content = f"{self.user.strip().lower()}||{self.assistant.strip().lower()}"
        return hashlib.md5(content.encode()).hexdigest()


@dataclass
class ValidationResult:
    """Result of validating a single example."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DatasetStats:
    """Summary statistics for a dataset."""
    total_raw: int
    after_validation: int
    after_dedup: int
    train_count: int
    val_count: int
    test_count: int
    removed_invalid: int
    removed_duplicates: int


class Contract:
    """
    Defines the input/output contract for a fine-tuning dataset.
    All examples must pass the contract before entering the pipeline.
    """

    def __init__(
        self,
        system_prompt: str,
        min_user_length: int = 10,
        max_user_length: int = 2000,
        min_assistant_length: int = 20,
        max_assistant_length: int = 1000,
        required_output_words: Optional[list[str]] = None,
        forbidden_output_words: Optional[list[str]] = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.min_user_length = min_user_length
        self.max_user_length = max_user_length
        self.min_assistant_length = min_assistant_length
        self.max_assistant_length = max_assistant_length
        self.required_output_words = required_output_words or []
        self.forbidden_output_words = forbidden_output_words or []

    def validate(self, example: Example) -> ValidationResult:
        """Validate a single example against the contract."""
        errors = []
        warnings = []

        # Length checks
        if len(example.user) < self.min_user_length:
            errors.append(
                f"User message too short ({len(example.user)} chars, min {self.min_user_length})"
            )
        if len(example.user) > self.max_user_length:
            warnings.append(
                f"User message very long ({len(example.user)} chars) - consider trimming"
            )
        if len(example.assistant) < self.min_assistant_length:
            errors.append(
                f"Assistant response too short ({len(example.assistant)} chars, "
                f"min {self.min_assistant_length})"
            )
        if len(example.assistant) > self.max_assistant_length:
            warnings.append(
                f"Assistant response very long ({len(example.assistant)} chars) - "
                "check if it was truncated"
            )

        # Forbidden content
        for word in self.forbidden_output_words:
            if word.lower() in example.assistant.lower():
                errors.append(f"Forbidden word in output: '{word}'")

        # Required content check (at least one must be present, not all)
        if self.required_output_words:
            found = any(
                w.lower() in example.assistant.lower()
                for w in self.required_output_words
            )
            if not found:
                warnings.append(
                    f"Output may not match expected format. "
                    f"Expected one of: {self.required_output_words}"
                )

        # Completeness check - truncation detection
        if example.assistant.endswith(("...", "and", "but", "the", "a", "an")):
            warnings.append("Assistant response may be truncated (ends mid-sentence)")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


class DatasetPipeline:
    """
    Five-step fine-tuning dataset pipeline:
    1. Validate (contract checks)
    2. Deduplicate (fingerprint-based)
    3. Human review summary (stats for annotator)
    4. Split (train/val/test)
    5. Write JSONL
    """

    def __init__(self, contract: Contract, seed: int = 42) -> None:
        self.contract = contract
        self.seed = seed
        self._raw: list[Example] = []
        self._valid: list[Example] = []
        self._deduped: list[Example] = []
        self._splits: dict[str, list[Example]] = {}

    def add(self, user: str, assistant: str, metadata: dict | None = None) -> None:
        """Add a raw example to the pipeline."""
        example = Example(
            system=self.contract.system_prompt,
            user=user,
            assistant=assistant,
            metadata=metadata or {},
        )
        self._raw.append(example)

    def add_batch(self, examples: list[dict]) -> None:
        """Add multiple raw examples. Each dict must have 'user' and 'assistant' keys."""
        for ex in examples:
            self.add(
                user=ex["user"],
                assistant=ex["assistant"],
                metadata=ex.get("metadata", {}),
            )

    def validate(self) -> tuple[list[Example], list[tuple[Example, ValidationResult]]]:
        """
        Run contract validation on all raw examples.
        Returns (valid_examples, rejected_with_reasons).
        """
        valid = []
        rejected = []

        for example in self._raw:
            result = self.contract.validate(example)
            if result.is_valid:
                valid.append(example)
                if result.warnings:
                    print(f"  WARNING in example '{example.user[:40]}...': {result.warnings}")
            else:
                rejected.append((example, result))

        self._valid = valid
        print(f"\nValidation: {len(valid)} valid, {len(rejected)} rejected from {len(self._raw)} total")

        if rejected:
            print(f"  First rejected example: '{rejected[0][0].user[:60]}'")
            print(f"  Errors: {rejected[0][1].errors}")

        return valid, rejected

    def deduplicate(self) -> list[Example]:
        """
        Remove exact and near-exact duplicates using fingerprinting.
        Keeps the first occurrence of each unique example.
        """
        seen_fingerprints = set()
        deduped = []

        for example in self._valid:
            fp = example.fingerprint()
            if fp not in seen_fingerprints:
                seen_fingerprints.add(fp)
                deduped.append(example)

        removed = len(self._valid) - len(deduped)
        print(f"\nDeduplication: removed {removed} duplicates, {len(deduped)} unique examples remain")

        self._deduped = deduped
        return deduped

    def split(
        self,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
    ) -> dict[str, list[Example]]:
        """
        Split examples into train/val/test with a fixed seed.
        Always shuffle before splitting to avoid ordering bias.
        """
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, (
            "Ratios must sum to 1.0"
        )

        examples = list(self._deduped)
        random.seed(self.seed)
        random.shuffle(examples)

        n = len(examples)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)

        self._splits = {
            "train": examples[:train_end],
            "val": examples[train_end:val_end],
            "test": examples[val_end:],
        }

        for split_name, split_examples in self._splits.items():
            print(f"  {split_name}: {len(split_examples)} examples")

        return self._splits

    def write_jsonl(self, output_dir: str) -> dict[str, str]:
        """
        Write each split to a JSONL file in the output directory.
        Returns dict of {split_name: file_path}.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        paths = {}

        for split_name, examples in self._splits.items():
            path = Path(output_dir) / f"{split_name}.jsonl"
            with open(path, "w", encoding="utf-8") as f:
                for example in examples:
                    f.write(json.dumps(example.to_messages(), ensure_ascii=False) + "\n")
            paths[split_name] = str(path)
            print(f"  Wrote {len(examples)} examples to {path}")

        return paths

    def stats(self) -> DatasetStats:
        """Return summary statistics for the pipeline run."""
        return DatasetStats(
            total_raw=len(self._raw),
            after_validation=len(self._valid),
            after_dedup=len(self._deduped),
            train_count=len(self._splits.get("train", [])),
            val_count=len(self._splits.get("val", [])),
            test_count=len(self._splits.get("test", [])),
            removed_invalid=len(self._raw) - len(self._valid),
            removed_duplicates=len(self._valid) - len(self._deduped),
        )

    def run(self, output_dir: str = "./dataset_output") -> dict[str, str]:
        """
        Run the full pipeline: validate -> deduplicate -> split -> write.
        Returns paths to the written JSONL files.
        """
        print(f"\n{'='*60}")
        print("DATASET PIPELINE RUN")
        print(f"{'='*60}")
        print(f"Input: {len(self._raw)} raw examples")

        self.validate()
        self.deduplicate()

        print(f"\nSplit (seed={self.seed}):")
        self.split()

        print(f"\nWriting JSONL to {output_dir}:")
        paths = self.write_jsonl(output_dir)

        stats = self.stats()
        print(f"\n{'='*60}")
        print("PIPELINE SUMMARY")
        print(f"{'='*60}")
        print(f"  Raw examples:       {stats.total_raw}")
        print(f"  After validation:   {stats.after_validation} (-{stats.removed_invalid} invalid)")
        print(f"  After dedup:        {stats.after_dedup} (-{stats.removed_duplicates} duplicates)")
        print(f"  Train:              {stats.train_count}")
        print(f"  Val:                {stats.val_count}")
        print(f"  Test:               {stats.test_count}")

        return paths


# ---- Synthetic customer support dataset ----

SUPPORT_SYSTEM_PROMPT = (
    "You are a friendly customer support agent for Acme Software. "
    "Be direct, helpful, and warm. Answer the customer's question in 2-4 sentences. "
    "If you cannot resolve their issue, tell them you will escalate to a specialist."
)

SYNTHETIC_EXAMPLES = [
    {"user": "How do I reset my password?",
     "assistant": "To reset your password, click 'Forgot Password' on the login page and enter your email address. You'll receive a reset link within 2 minutes. If you don't see it, check your spam folder. Let me know if you run into any trouble!"},
    {"user": "I can't log in to my account. It says my password is wrong but I know it's right.",
     "assistant": "That's frustrating - let's get you back in. First, try the password reset flow: click 'Forgot Password' on the login page. If you're certain of your password, try clearing your browser cache or using a private window. Sometimes saved credentials cause this. If neither works, I'll escalate to our account team."},
    {"user": "What are your support hours?",
     "assistant": "Our support team is available Monday through Friday, 9am to 6pm Eastern Time. For urgent issues outside those hours, you can submit a ticket and we'll respond within 4 hours. Our help center at help.acme.com is available 24/7 for self-service."},
    {"user": "I was charged twice for my subscription this month.",
     "assistant": "I'm sorry about the double charge - that shouldn't happen. I can see your account and will flag this for our billing team to review immediately. You'll receive a refund for the duplicate charge within 3-5 business days. I'll send you a confirmation email once it's processed."},
    {"user": "How do I cancel my subscription?",
     "assistant": "You can cancel anytime from your Account Settings - go to Billing, then click 'Cancel Subscription'. Your access continues until the end of your current billing period. If you're canceling because of a specific issue, I'd love to help you resolve it first."},
    {"user": "Does your product integrate with Slack?",
     "assistant": "Yes, we have a native Slack integration that sends notifications directly to your workspace. To set it up, go to Settings > Integrations > Slack and follow the authorization steps. The setup takes about 2 minutes. Let me know if you hit any snags."},
    {"user": "My export is stuck at 0%. It's been an hour.",
     "assistant": "An export stuck at 0% for an hour indicates something went wrong with the job. Please cancel the export, wait 30 seconds, and restart it. If it hangs again, try with a smaller date range to rule out a size issue. I'll also flag your account for our infrastructure team to check for any underlying issues."},
    {"user": "Can I share my account with a teammate?",
     "assistant": "Account sharing isn't allowed under our terms of service, but you can add teammates as separate users. On our Team plan, you can invite up to 10 users from Settings > Team Members. If you're on the Individual plan, upgrading to Team is straightforward and your billing adjusts proactively."},
    {"user": "How do I export my data to CSV?",
     "assistant": "To export your data, go to Reports > Export and select 'CSV' as the format. You can filter by date range and data type before exporting. Large exports are processed in the background and you'll get an email with the download link when it's ready."},
    {"user": "I deleted some data by accident. Can I recover it?",
     "assistant": "Deleted data is recoverable within 30 days. Go to Settings > Data Management > Deleted Items to restore what you need. If it's been more than 30 days, I'll escalate to our data team - they may be able to recover it from backups depending on the type of data."},
    {"user": "Why is the app so slow today?",
     "assistant": "I'm checking our status page right now. If there's no active incident, the slowness may be specific to your account or region. Try a hard refresh (Ctrl+Shift+R on Windows, Cmd+Shift+R on Mac) and clear your cache. If it persists, share your account email and I'll investigate on our end."},
    {"user": "Is there a mobile app?",
     "assistant": "Yes! Our mobile app is available for iOS and Android. Search 'Acme Software' in the App Store or Google Play. It has feature parity with the web app for most tasks. Some advanced configuration options are web-only, but day-to-day work is fully supported on mobile."},
    {"user": "I'm getting an error that says 'API rate limit exceeded'.",
     "assistant": "This error means your account has hit the API call limit for your current plan. The limit resets at midnight UTC. If you need higher limits, I can show you our options for the API-heavy plan. Alternatively, adding exponential backoff to your integration will smooth out the request pattern and prevent this."},
    {"user": "Can I get a refund for this month?",
     "assistant": "Refunds are handled case by case. If you've had a service disruption or billing error, we'll absolutely make it right. If you're looking to cancel and want a partial refund, I'll pass that request to our billing team with a note on your usage. What's the reason behind the request?"},
    {"user": "The search is not returning results I know are there.",
     "assistant": "Search indexes update every 15 minutes, so very recent items may not appear yet. Make sure you're searching in the right workspace and that any active filters are not hiding the results. If you can share the name or ID of an item you expect to see, I'll check if it's indexed correctly on our end."},
    {"user": "How do I change my email address?",
     "assistant": "Go to Settings > Profile > Email Address and enter your new email. You'll receive a confirmation to the new address - click the link to confirm the change. If you no longer have access to your old email address, I'll handle the update manually after verifying your identity."},
    {"user": "I need an invoice for my last payment for accounting purposes.",
     "assistant": "Your invoices are in Settings > Billing > Invoice History. You can download any invoice as a PDF from there. If you need a specific format or need the invoice reissued with different details, reply here and I'll have our billing team generate a custom one for you."},
    {"user": "I upgraded my plan but the new features are not showing up.",
     "assistant": "Plan changes take effect immediately but occasionally require a page refresh or re-login to display. Try logging out and back in. If the features still don't appear after that, there may be a provisioning delay - I'll check your account status and manually trigger the upgrade if needed."},
    {"user": "Is my data secure? Where is it stored?",
     "assistant": "Your data is encrypted at rest (AES-256) and in transit (TLS 1.3). We store data in US-East AWS data centers with SOC2 Type II certification. If you need a full security report or have compliance requirements (HIPAA, GDPR), I can connect you with our security team for a proper review."},
    {"user": "How do I add a custom domain to my account?",
     "assistant": "Custom domains are available on Business and Enterprise plans. Go to Settings > Domains > Add Domain and follow the DNS verification steps. The verification typically takes 5-10 minutes. If you're on a lower plan and want to upgrade for this feature, I can show you the options."},
    # Near-duplicate intentionally included for dedup testing
    {"user": "How do I reset my password?",
     "assistant": "Click 'Forgot Password' on the login page and enter your email. A reset link arrives within 2 minutes."},
    # Example with a quality issue (too short) - will be caught by validation
    {"user": "When does support close?",
     "assistant": "6pm."},
    # More examples to reach 50+
    {"user": "Can I downgrade my plan?",
     "assistant": "Yes, you can downgrade at any time from Settings > Billing > Change Plan. The downgrade takes effect at your next billing cycle. If you're on an annual plan, the downgrade applies at renewal. Let me know if you want to compare features before deciding."},
    {"user": "I forgot which email I used to sign up.",
     "assistant": "If you have a rough idea of which email it might be, try a few on the login page - our password reset flow will confirm whether an account exists. If you're completely unsure, I can search by name or company if you share that information here."},
    {"user": "How many users can I have on the Team plan?",
     "assistant": "The Team plan supports up to 25 users. If you need more than 25, we'd recommend our Business plan which has no user cap. I can walk you through the pricing difference if that's helpful."},
    {"user": "Why does my dashboard show different numbers than the export?",
     "assistant": "Dashboard numbers are typically based on your local timezone, while exports default to UTC. Check the date range and timezone settings on both. If the numbers still don't reconcile after adjusting for timezone, share a screenshot and I'll investigate with our data team."},
    {"user": "Can I use the API on the free plan?",
     "assistant": "The free plan includes read-only API access with 100 calls per day. Write access and higher limits require a paid plan. Our documentation at api.acme.com has the full endpoint list and rate limit details for each plan tier."},
    {"user": "I need to migrate data from my old account to a new one.",
     "assistant": "Data migrations are handled by our team to ensure nothing is lost. Send me your old and new account emails and the type of data you need migrated. We typically complete account migrations within 24 hours. There's no charge for migrations within the same plan tier."},
    {"user": "The two-factor authentication code isn't working.",
     "assistant": "2FA codes are time-sensitive - make sure your device clock is synchronized (time drift of even 30 seconds will cause failures). If your clock is correct, try generating a new code. If you're locked out completely, I can initiate a recovery process after verifying your identity via your backup email."},
    {"user": "Can I get a trial of the Enterprise features?",
     "assistant": "Absolutely. I can set up a 14-day Enterprise trial on your account so you can evaluate the advanced features before committing. I'll enable it now - you should see the Enterprise menu items appear within 5 minutes. Let me know what specific features you want to test."},
    {"user": "My webhook stopped receiving events yesterday.",
     "assistant": "Webhook failures are usually caused by a timeout or 5xx response from your endpoint. Check your server logs for errors around the time the webhooks stopped. Our dashboard at Settings > Webhooks shows the delivery history and error details. If your endpoint is healthy, I'll re-queue the failed events."},
    {"user": "How do I set up SSO for my organization?",
     "assistant": "SSO is available on our Business and Enterprise plans via SAML 2.0. The setup guide is at docs.acme.com/sso and covers Okta, Azure AD, and generic SAML providers. If you're using a less common IdP, our implementation team can assist. Want me to schedule a setup call?"},
    {"user": "I'd like to give feedback about the product.",
     "assistant": "I love hearing feedback - it goes directly to our product team. You can also submit feature requests at feedback.acme.com where you can vote on existing ideas. What's on your mind?"},
    {"user": "How do I change the default currency in my account?",
     "assistant": "Currency is set at the organization level and can be changed in Settings > Organization > Billing Preferences. Note that changing currency applies to future invoices - existing invoices are not retroactively updated. If you need historical invoices reissued in a new currency, contact our billing team."},
    {"user": "The app crashes when I try to open a report.",
     "assistant": "I'm sorry about that crash. Please try a hard refresh first (Ctrl+Shift+R or Cmd+Shift+R). If the crash persists, open your browser console (F12 > Console) and copy any red error messages - that will help us diagnose it quickly. Which browser and version are you using?"},
    {"user": "Is there a way to bulk-delete records?",
     "assistant": "Yes - you can bulk select records by checking the box in the header row of any list view, then choose Delete from the action menu. For very large deletions (thousands of records), use the API with DELETE /records in batches to avoid timeouts. Do you want the API documentation link?"},
    {"user": "I have a GDPR data deletion request to fulfill.",
     "assistant": "GDPR deletion requests are handled under our DPA. Submit the request through Settings > Privacy > Data Requests with the subject's email address. We complete deletion within 30 days as required. If you need a deletion confirmation certificate, include that in the request form."},
    {"user": "Can I schedule reports to be emailed automatically?",
     "assistant": "Yes! Go to Reports, open any report, and click 'Schedule' in the top-right corner. You can set frequency (daily, weekly, monthly), format (PDF or CSV), and recipient email addresses. Scheduled reports run at midnight in your account timezone."},
    {"user": "My colleague can't see the project I shared with them.",
     "assistant": "Shared project access can take up to 5 minutes to propagate. If it's been longer, check that you shared with the correct email address (it must match their login email exactly). Also confirm their account role has at least Viewer access to your workspace. Send me both email addresses and I'll check the permissions directly."},
    {"user": "How do I connect a Zapier integration?",
     "assistant": "Our Zapier app is in the Zapier marketplace - search for 'Acme Software'. Create a Zap, choose your trigger, and when prompted for authentication use your API key from Settings > API Keys. Our Zapier help page at docs.acme.com/zapier lists all available triggers and actions."},
    {"user": "I accidentally shared a private document with everyone. How do I undo it?",
     "assistant": "Go to the document, click Share > Permissions and remove 'Everyone' or change it to Specific People. The change takes effect immediately. If the document contained sensitive data and you're concerned about who may have accessed it, I can pull an access log from our audit trail."},
    {"user": "What happens to my data if I cancel?",
     "assistant": "After cancellation your data is retained for 90 days in case you reactivate. After 90 days it is permanently deleted per our data retention policy. We recommend exporting your data before canceling. I can send you the export guide if that's helpful."},
    {"user": "Can I have multiple workspaces on one account?",
     "assistant": "Multiple workspaces are supported on Team, Business, and Enterprise plans. Each workspace has its own data, users, and settings. You can switch between workspaces from the account menu in the top-left corner. The free plan is limited to one workspace."},
    {"user": "The email notifications are going to my spam folder.",
     "assistant": "To prevent our emails from going to spam, add notifications@acme.com to your safe senders list or contacts. If you're on Gmail, open one of our emails and click 'Not Spam'. For organization-wide issues, your IT team can whitelist our sending domain (mail.acme.com) at the mail server level."},
    {"user": "I need to process more than the API rate limit allows. What are my options?",
     "assistant": "There are two paths: upgrade to our API-heavy plan which includes 10x the rate limit, or implement a queue on your side that throttles requests to stay within your current limit. For very high volumes (millions of calls/day), we offer custom rate limits on Enterprise contracts. What's your current call volume?"},
    {"user": "Is there an audit log I can check for user activity?",
     "assistant": "Yes, the audit log is in Settings > Security > Audit Log. It records all user sign-ins, data access, settings changes, and API activity with timestamps and IP addresses. The log is available for the last 12 months on Business and Enterprise plans. You can export it as CSV for compliance reporting."},
    {"user": "How do I rename a project?",
     "assistant": "Click the project name in the project header - it's directly editable inline. Press Enter or click elsewhere to save. The rename is immediate and visible to all project members. Project URLs do not change when you rename, so existing bookmarks still work."},
    {"user": "My team member got locked out after too many failed login attempts.",
     "assistant": "Accounts lock after 10 failed attempts for 15 minutes as a security measure. The lock clears automatically after 15 minutes. If they need immediate access, I can unlock it manually - send me their email address and I'll take care of it right now."},
    {"user": "Can I white-label the product for my clients?",
     "assistant": "White-labeling is available on our Enterprise plan. It includes custom domain, logo, color scheme, and email branding. If you're evaluating Enterprise features, I can set up a trial. Our partnerships team handles white-label contracts - want me to connect you with them?"},
]


def run_pipeline() -> None:
    """Run the full dataset pipeline on the synthetic customer support dataset."""
    contract = Contract(
        system_prompt=SUPPORT_SYSTEM_PROMPT,
        min_user_length=10,
        max_user_length=2000,
        min_assistant_length=30,  # "6pm." will fail this
        max_assistant_length=800,
        forbidden_output_words=["I don't know", "I cannot help"],
    )

    pipeline = DatasetPipeline(contract=contract, seed=42)
    pipeline.add_batch(SYNTHETIC_EXAMPLES)

    output_dir = "./dataset_output"
    paths = pipeline.run(output_dir=output_dir)

    print(f"\nDataset files:")
    for split_name, path in paths.items():
        print(f"  {split_name}: {path}")

    # Show one example from the training set
    print(f"\nSample training example:")
    if pipeline._splits.get("train"):
        sample = pipeline._splits["train"][0]
        print(json.dumps(sample.to_messages(), indent=2))


if __name__ == "__main__":
    run_pipeline()
