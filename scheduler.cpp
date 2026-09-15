#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <cctype>

struct Emergency {
    int id;
    std::string severity;
};

// Convert a string to uppercase, so matching doesn't care about case
std::string toUpper(const std::string& s) {
    std::string result = s;
    std::transform(result.begin(), result.end(), result.begin(), ::toupper);
    return result;
}

int priorityValue(const std::string& severity) {
    std::string upper = toUpper(severity);
    if (upper == "CRITICAL") return 1;
    if (upper == "MODERATE") return 2;
    if (upper == "LOW") return 3;
    return 4;
}

int main() {
    std::vector<Emergency> emergencies;
    int id;
    std::string severity;

    while (std::cin >> id >> severity) {
        emergencies.push_back({id, severity});
    }

    std::stable_sort(emergencies.begin(), emergencies.end(),
        [](const Emergency& a, const Emergency& b) {
            return priorityValue(a.severity) < priorityValue(b.severity);
        });

    for (const auto& e : emergencies) {
        std::cout << e.id << " " << e.severity << "\n";
    }

    return 0;
}