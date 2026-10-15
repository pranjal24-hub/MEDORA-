#include <iostream>
#include <vector>

#include "EmergencyRequest.h"
#include "SchedulingManager.h"
#include "RequestStatus.h"

using namespace std;

int main()
{
    vector<EmergencyRequest> requests;

    cout << "====================================" << endl;
    cout << " MEDORA Emergency Resource System" << endl;
    cout << "====================================" << endl;

    // Step 1: Enter emergency requests
    inputEmergencyRequests(requests);

    if (requests.empty())
    {
        cout << "No emergency requests entered." << endl;
        return 0;
    }

    // Step 2: Create scheduling and status managers
    SchedulingManager scheduler;
    RequestStatusManager statusManager;

    // Step 3: Submit requests to the scheduler
    for (const auto& request : requests)
    {
        scheduler.submitRequest(request);
        statusManager.registerRequest(request.requestId);
    }

    cout << "\nAll requests submitted successfully." << endl;

    // Step 4: Display pending requests
    scheduler.displayPendingRequests();

    // Step 5: Process requests according to scheduling priority
    while (scheduler.hasPendingRequests())
    {
        EmergencyRequest request = scheduler.processNextRequest();

        // Update request status
        statusManager.updateStatus(
            request.requestId,
            RequestState::Processing
        );

        cout << "\nProcessing Request ID: "
             << request.requestId << endl;

        statusManager.displayStatus(request.requestId);

        // Demonstration only: mark the request completed
        statusManager.updateStatus(
            request.requestId,
            RequestState::Completed
        );

        statusManager.displayStatus(request.requestId);
    }

    cout << "\n====================================" << endl;
    cout << " All requests processed." << endl;
    cout << " MEDORA execution completed." << endl;
    cout << "====================================" << endl;

    return 0;
}
Authentic