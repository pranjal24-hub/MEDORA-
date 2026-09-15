#include <iostream>
#include <algorithm>
#include "PriorityScheduling.h"

using namespace std;

void prioritySchedule(vector<EmergencyRequest>& requests)
{
    sort(requests.begin(), requests.end(),
        [](const EmergencyRequest& a, const EmergencyRequest& b)
        {
            if (a.severity != b.severity)
            {
                return a.severity > b.severity;
            }

            // If severity is same, give preference
            // to the request waiting longer.
            return a.waitingTime > b.waitingTime;
        });
}

void displaySchedule(const vector<EmergencyRequest>& requests)
{
    cout << "\n--- MEDORA Priority Scheduling Result ---" << endl;

    for (const auto& request : requests)
    {
        cout << "\nRequest ID: " << request.requestId;
        cout << " | Ambulance: " << request.ambulanceId;
        cout << " | Severity: " << request.severity;
        cout << " | Waiting Time: " << request.waitingTime
             << " minutes";
    }

    cout << endl;
}