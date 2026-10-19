// Reply Triage: what does this reply want, and is it an opt-out?
//
// Phrase groups are scanned strongest-first and each match is blanked, so
// "not interested" is counted as negative and never again as "interested".
// Any opt-out phrase makes the label opt_out whatever else matched: for
// compliance a false "opt-out" costs a human glance, a missed one costs a
// violation. Advisory only -- the existing reply classifier and suppression
// path stay authoritative; this agent flags disagreements for review.
#include <sstream>

#include "vectorae/agents.hpp"
#include "vectorae/text.hpp"

namespace vectorae {

const std::vector<PhraseGroup>& triage_groups() {
    static const std::vector<PhraseGroup> groups = {
        {"bounce", 3.0, {"delivery status notification", "undeliverable", "mailbox not found",
                         "address not found", "message not delivered", "delivery has failed",
                         "mail delivery subsystem", "recipient address rejected"}},
        {"out_of_office", 3.0, {"out of office", "out of the office", "on vacation", "on annual leave",
                                "on leave until", "away until", "automatic reply", "auto-reply",
                                "autoreply", "limited access to email", "i will be back",
                                "i'll be back on", "returning on"}},
        {"opt_out", 4.0, {"unsubscribe", "remove me", "take me off", "stop emailing", "stop contacting",
                          "stop sending", "do not contact", "don't contact", "do not email",
                          "don't email", "opt out", "opt-out", "remove my email", "no more emails",
                          "leave me alone"}},
        {"negative", 2.0, {"not interested", "no thanks", "no thank you", "not a fit", "not for us",
                           "we're all set", "we are all set", "already have a solution",
                           "please don't", "not looking"}},
        {"not_now", 2.0, {"not right now", "not at the moment", "maybe later", "next quarter",
                          "next year", "in a few months", "circle back", "reach back out",
                          "not a priority", "check back", "too busy"}},
        {"referral", 2.0, {"the right person", "better person", "reach out to", "contact my colleague",
                           "speak with my colleague", "cc'ing", "looping in", "forwarding this to",
                           "in charge of"}},
        {"interested", 2.0, {"interested", "tell me more", "sounds good", "sounds interesting",
                             "let's talk", "lets talk", "let's chat", "happy to chat", "book a call",
                             "schedule a call", "set up a call", "set up a time", "when are you free",
                             "what times work", "send me more", "more information", "more info",
                             "send over", "pricing", "demo", "calendar link"}},
    };
    return groups;
}

std::string strip_quoted(const std::string& text) {
    std::istringstream in(text);
    std::string line, out;
    bool first = true;
    while (std::getline(in, line)) {
        const std::string t = ascii_lower(trim(line));
        if (starts_with(t, ">")) continue;
        if ((starts_with(t, "on ") && ends_with(t, "wrote:")) ||
            starts_with(t, "-----original message") || starts_with(t, "from:")) {
            break;
        }
        if (!first) out += '\n';
        out += line;
        first = false;
    }
    return out;
}

Triage triage_reply(const std::string& subject, const std::string& body) {
    std::string text = ascii_lower(subject + "\n" + strip_quoted(body));
    Triage t;
    double total = 0.0;
    for (const auto& g : triage_groups()) {
        double score = 0.0;
        for (const auto& p : g.phrases) {
            const int n = take_phrase(text, p);
            if (n > 0) {
                score += g.weight * n;
                t.matched.emplace_back(g.category, p);
            }
        }
        t.scores.emplace_back(g.category, score);
        total += score;
    }
    auto score_of = [&](const std::string& c) {
        for (const auto& s : t.scores) if (s.first == c) return s.second;
        return 0.0;
    };
    t.opt_out = score_of("opt_out") > 0.0;
    double top = 0.0;
    if (t.opt_out) { t.label = "opt_out"; top = score_of("opt_out"); }
    else if (score_of("bounce") > 0.0) { t.label = "bounce"; top = score_of("bounce"); }
    else if (score_of("out_of_office") > 0.0) { t.label = "out_of_office"; top = score_of("out_of_office"); }
    else {
        t.label = "unclear";
        for (const char* c : {"negative", "not_now", "referral", "interested"}) {
            if (score_of(c) > top) { top = score_of(c); t.label = c; }
        }
    }
    t.confidence = total > 0.0 ? top / (total + 1.0) : 0.0;
    return t;
}

}  // namespace vectorae
