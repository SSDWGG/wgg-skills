# Platform Access Notes

This reference is for deciding how to collect public social activity. Use current official docs before writing code against a platform, because API tiers, scopes, and endpoints change often.

## X / Twitter

Best fit for direct posts by a known target account.

- Resolve handles to user ids with the X API user lookup endpoints.
- Pull authored posts with the user timeline endpoint.
- Pull target mentions with the mentions timeline endpoint when the user asks for surrounding discourse.
- Use search endpoints for broader topic or name searches, subject to the account's access tier.

Official docs:

- X API documentation: `https://developer.x.com/en/docs/x-api`
- User lookup: `https://developer.x.com/en/docs/x-api/users/lookup/introduction`
- User post timeline: `https://developer.x.com/en/docs/x-api/tweets/timelines/introduction`
- Search posts: `https://developer.x.com/en/docs/x-api/tweets/search/introduction`

Record the `id`, `author_id`, `created_at`, `text`, public metrics when available, and canonical URL. For public figures, verify that the handle is the real account before reporting.

## Facebook and Instagram

Do not assume arbitrary personal profile monitoring is available through ordinary Graph API access. Meta access depends on account type, permissions, app review, and product eligibility.

For broad public-content monitoring, check whether the user has access to Meta Content Library and API. Meta describes it as access to public content from Facebook Pages, Posts, Groups, Events and from Instagram creator/business accounts, aimed at research and analysis use cases.

Official docs and entry points:

- Meta Content Library and API overview: `https://transparency.meta.com/researchtools/meta-content-library/`
- Meta announcement for Content Library and API: `https://about.fb.com/news/2023/11/meta-content-library-and-api/`
- Meta Graph API docs: `https://developers.facebook.com/docs/graph-api/`
- Instagram Platform docs: `https://developers.facebook.com/docs/instagram-platform/`

If the user lacks approved Meta access, fall back to verified public profile URLs, public post URLs, embedded posts in articles, or web search leads. Label these as public-web collection, not official API coverage.

## Public Web and News

Use web search to find public profile URLs, post embeds, announcements, and news events. Treat search results as leads until a stable source URL supports the claim.

Good public-web query patterns:

- `"target name" site:x.com OR site:twitter.com`
- `"target name" site:instagram.com/p`
- `"target name" site:facebook.com`
- `"target handle" "posted" OR "said"`
- `"target name" after:YYYY-MM-DD before:YYYY-MM-DD`

When reporting from news coverage, distinguish "the target posted" from "a publication reports that the target posted." Link both the article and the original post when possible.

## Safety and Compliance Boundaries

Allowed:

- Public posts from official or verified accounts.
- Public mentions, public pages, and public news/events.
- User-provided exported data or credentials they are authorized to use.
- Summaries, metadata tables, and short excerpts with source links.

Disallowed:

- Circumventing authentication, privacy controls, rate limits, or anti-bot systems.
- Monitoring private accounts, closed groups, DMs, hidden stories, or deleted content without authorization.
- Creating sockpuppet accounts or using compromised credentials.
- Presenting unverified reposts or screenshots as original evidence.
