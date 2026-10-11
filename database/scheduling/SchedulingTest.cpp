#include <iostream>
#include <vector>
#include <cassert>

#include "EmergencyRequest.h"
#include "PriorityScheduling.h"
#include "AgingPolicy.h"

using namespace std;

void testPriorityScheduling()
{
    cout << "\nTest 1: Priority Scheduling" << endl;

    vector<EmergencyRequest> requests =
    {
        {1, "AMB101", "Aman", 2, "Oxygen", 10},
        {2, "AMB102", "Riya", 5, "ICU", 5},
        {3, "AMB103", "Rahul", 4, "Ventilator", 15}
    };

    prioritySchedule(requests);

    assert(requests[0].requestId == 2);
    assert(requests[1].requestId == 3);
    assert(requests[2].requestId == 1);

    cout << "Priority Scheduling Test Passed!" << endl;
}

void testAgingPolicy()
{
    cout << "\nTest 2: Aging Policy" << endl;

    vector<EmergencyRequest> requests =
    {
        {1, "AMB101", "Aman", 2, "Oxygen", 20},
        {2, "AMB102", "Riya", 4, "ICU", 5},
        {3, "AMB103", "Rahul", 3, "Ventilator", 10}
    };

    applyAgingPolicy(requests, 5);

    for (const auto& request : requests)
    {
        cout << "Request ID: " << request.requestId
             << " | Severity: " << request.severity
             << " | Waiting Time: " << request.waitingTime
             << " minutes" << endl;
    }

    assert(requests[0].requestId == 1);

    cout << "Aging Policy Test Passed!" << endl;
}

int main()
{
    cout << "===== MEDORA Scheduling Tests =====" << endl;

    testPriorityScheduling();
    testAgingPolicy();

    cout << "\nAll scheduling tests completed successfully!"
         << endl;

    return 0;
}