// ASCII text helpers shared by reply triage and the claim checker.
//
// Everything here is byte-wise ASCII on purpose: app/agents/reference.py does
// the same thing on Python strings (ASCII-only lowercase and alnum tests), so
// both implementations see the same phrases at the same boundaries whatever
// the input's non-ASCII content.
#pragma once

#include <string>
#include <utility>
#include <vector>

namespace vectorae {

inline bool is_alnum(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

inline bool is_digit(char c) { return c >= '0' && c <= '9'; }

inline std::string ascii_lower(const std::string& s) {
    std::string out(s);
    for (char& c : out) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return out;
}

// Counts occurrences of `phrase` in `text` at word boundaries (a boundary is
// only required next to an alphanumeric end of the phrase) and blanks each
// match with spaces, so a later, weaker phrase cannot match the same words.
inline int take_phrase(std::string& text, const std::string& phrase) {
    if (phrase.empty()) return 0;
    const bool need_before = is_alnum(phrase.front());
    const bool need_after = is_alnum(phrase.back());
    int count = 0;
    std::size_t pos = 0;
    while ((pos = text.find(phrase, pos)) != std::string::npos) {
        const std::size_t end = pos + phrase.size();
        const bool ok_before = !need_before || pos == 0 || !is_alnum(text[pos - 1]);
        const bool ok_after = !need_after || end == text.size() || !is_alnum(text[end]);
        if (ok_before && ok_after) {
            ++count;
            for (std::size_t i = pos; i < end; ++i) text[i] = ' ';
            pos = end;
        } else {
            pos += 1;
        }
    }
    return count;
}

inline std::string trim(const std::string& s) {
    const char* ws = " \t\r";
    const auto b = s.find_first_not_of(ws);
    if (b == std::string::npos) return "";
    const auto e = s.find_last_not_of(ws);
    return s.substr(b, e - b + 1);
}

inline bool starts_with(const std::string& s, const std::string& p) {
    return s.size() >= p.size() && s.compare(0, p.size(), p) == 0;
}

inline bool ends_with(const std::string& s, const std::string& p) {
    return s.size() >= p.size() && s.compare(s.size() - p.size(), p.size(), p) == 0;
}

}  // namespace vectorae
