export interface EmailTemplatePreset {
  id: string;
  name: string;
  subject: string;
  body: string;
}

export interface SignatureTemplatePreset {
  id: string;
  name: string;
  body: string;
}

export const customTemplateId = "custom";
export const customSignatureId = "custom";

export const defaultEmailSignature = "Best,\n{{your_name}}";

export const defaultEmailTemplate =
  'Subject: quick site note\n\nBody:\nHi {{first_name}},\n\nI took a quick look at {{company}} and noticed one specific website opportunity: {{top_issue}}.\n\nFor a {{industry}} business, that can mean visitors leave before they understand why to choose you.\n\nI help companies improve websites and add practical AI systems so more of the traffic they already have turns into leads and sales.\n\nWant me to send a short teardown with the 2-3 fixes I would prioritize?\n\n{{signature}}';

export const signatureTemplates: SignatureTemplatePreset[] = [
  {
    id: "simple",
    name: "Simple",
    body: "Best,\n{{your_name}}",
  },
  {
    id: "service",
    name: "Website + AI Services",
    body: "Best,\n{{your_name}}\nWebsite development and AI services",
  },
  {
    id: "calendar",
    name: "Calendar CTA",
    body: "Best,\n{{your_name}}\n{{calendar_link}}",
  },
];

export const emailTemplates: EmailTemplatePreset[] = [
  {
    id: "recent-event",
    name: "Tie to a Recent Event",
    subject: "Congrats!",
    body: "Hi {{name}},\n\nJust saw the news about {{trigger_event}}. Congrats!\n\nUsually when this happens, improving the website and adding practical AI systems becomes a priority. So I thought you might be interested in how we help companies turn new attention into more qualified leads.\n\nI know things at {{company}} must be busy now, but if you'd like to learn more, let's set up a quick call.\n\nHow does {{specific_day_and_time}} look on your calendar?\n\n{{signature}}",
  },
  {
    id: "aida",
    name: "AIDA Formula",
    subject: "Time Saving Software",
    body: "Hi {{name}},\n\nWhat would you do with an extra 10 hours each week?\n\nI ask because better websites and practical AI workflows can remove repetitive work while helping more visitors become leads.\n\nI'd love to set up a time to walk you through a personalized idea for {{company}}. Would you have some free time next week to connect?\n\n{{signature}}",
  },
  {
    id: "direct",
    name: "Direct Approach",
    subject: "10x {{company}} traction in 10 minutes",
    body: "Hello {{name}},\n\nI have an idea I can explain in 10 minutes that could help {{company}} get more of its best customers from the traffic it already has.\n\nIt is based on what I noticed while reviewing your website: {{top_issue}}.\n\n{{name}}, let's schedule a quick 10-minute call so I can share the idea with you. When works best?\n\n{{signature}}",
  },
  {
    id: "three-sentence",
    name: "3-Sentence Format",
    subject: "Quick Question",
    body: "Hi {{name}},\n\nMy name is {{your_name}}, and I'll keep this quick.\n\nI help businesses improve their websites and add practical AI services so more visitors become leads and more internal work gets automated.\n\nCould I have ten minutes next week to show one specific opportunity I found for {{company}}?\n\n{{signature}}",
  },
  {
    id: "introduction-request",
    name: "Introduction Request",
    subject: "Introduction to {{person_name}}",
    body: "Hi {{name}},\n\nI was looking to get introduced to {{person_name}} from {{company}}, and saw you may be connected to them.\n\nI'm not sure how well you know them, but if the relationship is strong, I'd appreciate an introduction to chat about ways our website development and AI services could help {{company}} grow.\n\nPlease let me know if you feel comfortable doing this and I'll forward a proper request you can pass along.\n\n{{signature}}",
  },
  {
    id: "bab",
    name: "Before-After-Bridge",
    subject: "A better way to manage {{process}}",
    body: "Hi {{name}},\n\nIf you're like most busy teams, you know how frustrating it is when a website gets traffic but does not turn enough of it into leads.\n\nA clearer website plus targeted AI workflows can create a smoother path from visitor interest to sales conversations.\n\nIf you'd be willing to give me ten minutes, I'll show you the same kind of opportunity for {{company}}. What's the best time next week?\n\n{{signature}}",
  },
  {
    id: "competitor",
    name: "Competitor Mention",
    subject: "Question about {{competitor_product}}",
    body: "Hi {{name}},\n\nI ran across {{company}}'s website and noticed a few areas where the experience could be sharper for visitors.\n\nI run {{your_company}}, a website development and AI services team. We help businesses create clearer, faster websites and automate key sales or service workflows.\n\nIf you're up for it, I would love to jump on a quick call and share how we could make {{company}}'s site stronger.\n\nWould {{date_and_time}} be a good time?\n\n{{signature}}",
  },
  {
    id: "pas",
    name: "Problem-Agitate-Solve",
    subject: "Your daily to-do list",
    body: "Hi {{name}},\n\nWhen's the last time your website handled more of the selling for you?\n\nIf the site is unclear or missing trust signals, people leave quietly and your team has to work harder to make up the gap.\n\nI help businesses improve their websites and add practical AI workflows so more visitors turn into qualified conversations.\n\nOpen to a personalized idea next week?\n\n{{signature}}",
  },
  {
    id: "right-person",
    name: "Right Person Outreach",
    subject: "Right person at {{company}}?",
    body: "Hi {{name}},\n\nI'm {{your_name}}, and I lead business development at {{your_company}}. We help companies improve websites and add practical AI services that support lead generation and growth.\n\nBased on what I found on {{company}}'s website, you might be the right person, or at least able to point me in the right direction.\n\nI'd like to speak with whoever owns website performance, lead generation, or AI automation. If it's you, would you be open to a 10-minute call on {{time_and_date}}?\n\n{{signature}}",
  },
  {
    id: "ppp",
    name: "Praise-Picture-Push",
    subject: "Great job at {{event}}",
    body: "Hi {{name}},\n\nCongrats! I just saw {{recent_praise_or_event}}.\n\nAs {{company}} gets more attention, it's natural for the website to carry more of the first impression and lead generation work. I noticed one opportunity that could make that path clearer: {{top_issue}}.\n\nCan I have ten minutes next week to show you what I mean?\n\n{{signature}}",
  },
  {
    id: "visitor-follow-up",
    name: "Website Visitor Follow-Up",
    subject: "Question about your visit to {{website}}",
    body: "Hi {{name}},\n\nYou recently visited {{website}} and {{took_this_action}}.\n\nIf you're interested in {{content_topic}}, I can recommend a couple of additional resources.\n\nWe also offer website development and AI services that can help you {{achieve_specific_result}}.\n\nAre you free for a call tomorrow at {{two_possible_times}} to discuss this further?\n\n{{signature}}",
  },
  {
    id: "resource-share",
    name: "Valuable Resource Share",
    subject: "Thought you might like this article",
    body: "Hi {{name}},\n\nYour latest article on {{subject}} got me thinking.\n\nI found this article on {{article_title}} that may be useful to you and your team:\n{{link}}\n\nHope you find it helpful. Keep up the great work.\n\n{{signature}}",
  },
  {
    id: "status-quo",
    name: "Status Quo Challenge",
    subject: "Productivity at {{company}}",
    body: "Hi {{name}},\n\nMy name is {{your_name}} with {{your_company}}.\n\nWe help busy teams improve websites and use practical AI systems to free up time for higher-priority growth work.\n\nI wanted to learn what website and automation tools you're currently using and show you one idea I noticed for {{company}}.\n\nAre you available for a brief call next week?\n\n{{signature}}",
  },
  {
    id: "gated-content",
    name: "Gated Content Follow-Up",
    subject: "Question about the {{content_name}} you downloaded",
    body: "Hi {{name}},\n\nYou recently visited our website and downloaded {{content_name}}. Did you find it useful?\n\nDid you download it just to learn more about {{content_topic}}, or are you looking for a cost-effective solution?\n\nI did some research on {{company}} and noticed this opportunity:\n{{top_issue}}\n\nHave you thought about fixing this?\n\n{{signature}}",
  },
  {
    id: "linkedin-follow-up",
    name: "LinkedIn Follow-Up",
    subject: "Great to connect, {{name}}",
    body: "Hi {{name}},\n\nThanks for accepting my LinkedIn request!\n\nWhen I noticed {{trigger_event}}, I figured the timing might be good to share a quick idea for {{company}}.\n\nI help teams improve websites and add practical AI services so more traffic becomes leads and more repetitive work gets automated.\n\nIf it sparks any ideas, happy to swap notes next week.\n\n{{signature}}",
  },
  {
    id: "sustainability",
    name: "Sustainability Pitch",
    subject: "Cutting waste by Q4; idea for {{company}}",
    body: "Hi {{name}},\n\nSaw {{company}}'s sustainability update and noticed {{remaining_pain}}.\n\nOne fast win can be using the website and practical AI workflows to reduce manual steps, duplicate intake, and wasted team time.\n\nOpen to a 12-minute chat next week? If it's not your remit, would you point me to whoever owns the initiative?\n\n{{signature}}",
  },
  {
    id: "voice-note",
    name: "Video/Voice Demo Invitation",
    subject: "45-sec voice note for {{name}}",
    body: "Hi {{name}},\n\nI recorded a quick voice memo after reviewing {{company}}'s website. I think you'll find it useful: {{voice_link}}\n\nIt covers one specific opportunity I noticed: {{top_issue}}.\n\nIf the idea resonates, feel free to grab a time here: {{calendar_link}}. No pressure if now isn't ideal.\n\nLooking forward to talking soon,\n{{your_name}}",
  },
  {
    id: "homepage-conversions",
    name: "Homepage Conversions",
    subject: "{{company}}'s homepage -> more signups",
    body: "Hi {{first_name}},\n\nTook a quick look at {{company}}'s site. You're clearly driving interest, but the homepage appears to ask visitors to do multiple things at once, which usually drags conversions down.\n\nWe redesign for one clear action, and for {{industry}} clients that can lift signups or sales without touching ad spend.\n\nWorth a 2-minute look at what I'd change?\n\n{{signature}}",
  },
  {
    id: "page-speed",
    name: "Page Speed / Core Web Vitals",
    subject: "{{company}} mobile speed",
    body: "Hi {{first_name}},\n\nI took a quick look at {{company}}'s site and noticed performance could be a revenue lever.\n\nIf mobile pages feel slow, traffic you're already paying for can bounce before the page even earns attention. We fix this as part of a rebuild and pair it with clearer conversion paths.\n\nWant the speed and UX breakdown?\n\n{{signature}}",
  },
  {
    id: "credibility-gap",
    name: "Outdated Design / Credibility",
    subject: "does {{company}}'s site match the product?",
    body: "Hi {{first_name}},\n\n{{company}} looks like it has a real offer, but the website may not be giving visitors enough confidence quickly enough.\n\nFor a brand at your stage, that credibility gap can cost deals before a single conversation happens.\n\nHappy to show you 2-3 quick fixes that would close it. Useful?\n\n{{signature}}",
  },
  {
    id: "funding-trigger",
    name: "Funding / Rebrand / Launch",
    subject: "congrats on the {{round}}",
    body: "Hi {{first_name}},\n\nCongrats on the {{round}}. Big milestone.\n\nUsually the next step is making sure the site can carry the new attention: investors, press, partners, and a wave of first-time visitors all landing at once.\n\nWe help {{industry}} teams ship a launch-ready site fast and add practical AI workflows around lead capture.\n\nIf a refresh is on the roadmap this quarter, worth a short chat?\n\n{{signature}}",
  },
  {
    id: "social-proof",
    name: "Social Proof / Comparable Result",
    subject: "website growth idea for {{company}}",
    body: "Hi {{first_name}},\n\nWe recently helped a {{industry}} business improve its website around clearer messaging, stronger trust signals, and a simpler path to inquiry.\n\nSince {{company}} appears to be in a similar spot, the same approach may transfer well.\n\nHappy to walk you through what I'd change on your site. Useful?\n\n{{signature}}",
  },
  {
    id: "referral",
    name: "Referral / Warm Intro",
    subject: "{{mutual_contact}} suggested I reach out",
    body: "Hi {{first_name}},\n\n{{mutual_contact}} mentioned {{company}} might be rethinking the website and thought our work could be relevant.\n\nWe design and build websites for {{industry}} brands and add practical AI systems where they can support growth.\n\nNot sure if it's on your radar right now, but if it is, I'd be glad to show a couple of recent projects close to what you'd need.\n\nWorth a quick look?\n\n{{signature}}",
  },
  {
    id: "mobile-bounce",
    name: "Mobile Experience / Bounce",
    subject: "{{company}} on mobile",
    body: "Hi {{first_name}},\n\nI opened {{company}}'s site on mobile and noticed the experience could be easier for small-screen visitors.\n\nEvery awkward tap is a visitor you already earned, quietly leaving. We rebuild mobile-first so the experience matches what people expect.\n\nWant a quick rundown of what may be tripping people up?\n\n{{signature}}",
  },
  {
    id: "free-audit",
    name: "Quick-Win Free Audit",
    subject: "free teardown of your homepage",
    body: "Hi {{first_name}},\n\nI looked at {{company}}'s homepage. There are 2-3 specific things in the layout and messaging that may be costing conversions.\n\nHappy to send a short, no-strings teardown as a quick video. Even if you never work with us, you keep the fixes.\n\nWant me to record it?\n\n{{signature}}",
  },
  {
    id: "re-engagement",
    name: "Re-Engagement",
    subject: "still thinking about the site?",
    body: "Hi {{first_name}},\n\nCircling back. I know a redesign is easy to push to later. If now's not the time, no worries at all.\n\nIf it's still on your mind, the offer stands: a quick, free teardown of {{company}}'s homepage with the 2-3 fixes I'd prioritize, no commitment.\n\nWant it?\n\n{{signature}}",
  },
  {
    id: "breakup",
    name: "Breakup Email",
    subject: "should I stop?",
    body: "Hi {{first_name}},\n\nI've reached out a couple of times about refreshing {{company}}'s site. I haven't heard back, so I'll assume the timing isn't right and close things out on my end.\n\nIf that changes, just reply and I'll pick it back up. Either way, wishing the team a strong quarter.\n\n{{signature}}",
  },
];

export function composeTemplate(
  template: EmailTemplatePreset,
  signature: SignatureTemplatePreset | null,
) {
  const signatureBody = signature?.body || "{{signature}}";
  const body = template.body.includes("{{signature}}")
    ? template.body.replaceAll("{{signature}}", signatureBody)
    : `${template.body}\n\n${signatureBody}`;
  return `Template: ${template.name}\nSubject: ${template.subject}\n\nBody:\n${body}`;
}

