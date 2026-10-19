// Claim & Compliance Check: risky wording in a draft before a human approves it.
//
// Flags guarantees, superlatives, unsourced numbers, false urgency, spam
// triggers, a "Re:"/"Fwd:" subject on a first touch (a deceptive subject line
// under CAN-SPAM), a shouting subject and stacked exclamation marks. Advisory:
// app/services/claim_verification.py and guardrails.py remain the send-time
// gates; this agent reports what a reviewer should look at.
#include "vectorae/agents.hpp"
#include "vectorae/text.hpp"

namespace vectorae {

const std::vector<ClaimRule>& claim_rules() {
    static const std::vector<ClaimRule> rules = {
        {"unverifiable_guarantee", "high", {"guaranteed", "guarantees", "guarantee", "100%",
                                            "risk-free", "risk free", "no risk", "zero risk"}},
        {"superlative", "medium", {"best in class", "best-in-class", "#1", "number one", "world-class",
                                   "world class", "industry-leading", "industry leading",
                                   "market leader", "the only", "unbeatable"}},
        {"false_urgency", "medium", {"act now", "limited time", "last chance", "urgent", "expires today",
                                     "only today", "don't miss out", "before it's too late",
                                     "final notice"}},
        {"spam_trigger", "low", {"click here", "free money", "winner", "no obligation", "cash bonus",
                                 "$$$", "earn money", "double your"}},
    };
    return rules;
}

int severity_points(const std::string& severity) {
    if (severity == "high") return 30;
    if (severity == "medium") return 12;
    return 4;
}

namespace {

// "40%", "40 %", "2.5%", "3x" not glued to a preceding word or number.
void numeric_claims(const std::string& t, std::vector<Finding>& out) {
    const std::size_t n = t.size();
    std::size_t i = 0;
    while (i < n) {
        if (is_digit(t[i]) && (i == 0 || (!is_alnum(t[i - 1]) && t[i - 1] != '.'))) {
            std::size_t j = i;
            while (j < n && (is_digit(t[j]) || t[j] == '.')) ++j;
            std::size_t k = j;
            if (k < n && t[k] == ' ') ++k;
            if (k < n && t[k] == '%') {
                out.push_back({"numeric_claim", "medium", t.substr(i, k + 1 - i)});
            } else if (j < n && t[j] == 'x' && (j + 1 == n || !is_alnum(t[j + 1]))) {
                out.push_back({"numeric_claim", "medium", t.substr(i, j + 1 - i)});
            }
            i = j;
        } else {
            ++i;
        }
    }
}

}  // namespace

ClaimReport check_claims(const std::string& subject, const std::string& body, bool first_touch) {
    ClaimReport r;
    std::string text = ascii_lower(subject + "\n" + body);
    for (const auto& rule : claim_rules()) {
        for (const auto& p : rule.phrases) {
            const int n = take_phrase(text, p);
            for (int c = 0; c < n; ++c) r.findings.push_back({rule.code, rule.severity, p});
        }
    }
    numeric_claims(text, r.findings);

    const std::string subj = ascii_lower(trim(subject));
    if (first_touch && (starts_with(subj, "re:") || starts_with(subj, "fwd:") || starts_with(subj, "fw:"))) {
        r.findings.push_back({"deceptive_subject", "high", subj.substr(0, subj.find(':') + 1)});
    }
    int letters = 0, upper = 0;
    for (char c : subject) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) {
            ++letters;
            if (c >= 'A' && c <= 'Z') ++upper;
        }
    }
    if (letters >= 8 && upper * 10 > letters * 6) {
        r.findings.push_back({"shouting_subject", "low", subject});
    }
    int bangs = 0;
    for (char c : subject + body) bangs += c == '!';
    if (bangs >= 3) r.findings.push_back({"excessive_exclamation", "low", std::to_string(bangs) + " x !"});

    bool high = false;
    for (const auto& f : r.findings) {
        r.risk += severity_points(f.severity);
        high = high || f.severity == "high";
    }
    if (r.risk > 100) r.risk = 100;
    r.verdict = high ? "block_recommended" : (r.risk >= 20 ? "review" : "pass");
    return r;
}

}  // namespace vectorae
