#include <iostream>
#include <algorithm>
#include <stdexcept>
#include "AgingPolicy.h"

using namespace std;

int calculateEffectivePriority(
    const EmergencyRequest& request,
    int agingInterval)
{
    if (agingInterval <= 0)
    {
        throw invalid_argument(
            "Aging interval must be greater than zero.");
    }

    int severity = max(1, min(5, request.severity));

    int agingBonus = max(0, request.waitingTime)
                     / agingInterval;

    return min(5, severity + agingBonus);
}

void applyAgingPolicy(
    vector<EmergencyRequest>& requests,
    int agingInterval)
{
    
    if (agingInterval <= 0)
    {
        throw invalid_argument(
            "Aging interval must be greater than zero.");
    }

    sort(requests.begin(), requests.end(),
        [agingInterval](
            const EmergencyRequest& a,
            const EmergencyRequest& b)
        {
            int priorityA =
                calculateEffectivePriority(a, agingInterval);

            int priorityB =
                calculateEffectivePriority(b, agingInterval);

            if (priorityA != priorityB)
            {
                return priorityA > priorityB;
            }

            if (a.waitingTime != b.waitingTime)
            {
                return a.waitingTime > b.waitingTime;
            }

            return a.requestId < b.requestId;
        });

    cout << "\nAging policy applied successfully."
         << endl;
}