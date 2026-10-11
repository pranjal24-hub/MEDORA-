#include <iostream>
#include <vector>
#include <stdexcept>

#include "SchedulingManager.h"
#include "AgingPolicy.h"

using namespace std;

void SchedulingManager::submitRequest(
    const EmergencyRequest& request)
{
    queue.addRequest(request);
}

void SchedulingManager::displayPendingRequests() const
{
    queue.displayQueue();
}

bool SchedulingManager::hasPendingRequests() const
{
    return !queue.isEmpty();
}

int SchedulingManager::getPendingCount() const
{
    return queue.size();
}

EmergencyRequest SchedulingManager::processNextRequest()
{
    if (queue.isEmpty())
    {
        throw runtime_error(
            "No pending emergency requests to process.");
    }

    
    vector<EmergencyRequest> pending;

    while (!queue.isEmpty())
    {
        pending.push_back(queue.getNextRequest());
    }

    
    applyAgingPolicy(pending);

    
    EmergencyRequest nextRequest = pending.front();


    for (size_t i = 1; i < pending.size(); i++)
    {
        queue.addRequest(pending[i]);
    }

    cout << "\n--- Processing Emergency Request ---" << endl;
    cout << "Request ID: " << nextRequest.requestId << endl;
    cout << "Ambulance ID: " << nextRequest.ambulanceId << endl;
    cout << "Patient: " << nextRequest.patientName << endl;
    cout << "Severity: " << nextRequest.severity << endl;
    cout << "Required Resource: "
         << nextRequest.requiredResource << endl;

    return nextRequest;
}