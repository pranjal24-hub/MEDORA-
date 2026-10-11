#include <iostream>
#include <stdexcept>
#include "RequestQueue.h"

using namespace std;

void RequestQueue::addRequest(const EmergencyRequest& request)
{
    requests.push_back(request);

    cout << "Emergency request added successfully."
         << endl;
}

bool RequestQueue::isEmpty() const
{
    return requests.empty();
}

int RequestQueue::size() const
{
    return static_cast<int>(requests.size());
}

EmergencyRequest RequestQueue::getNextRequest()
{
    if (requests.empty())
    {
        throw runtime_error("No emergency requests available.");
    }

    EmergencyRequest nextRequest = requests.front();

    requests.erase(requests.begin());

    return nextRequest;
}

void RequestQueue::displayQueue() const
{
    cout << "\n--- MEDORA Request Queue ---" << endl;

    if (requests.empty())
    {
        cout << "No pending emergency requests."
             << endl;
        return;
    }

    for (const auto& request : requests)
    {
        cout << "Request ID: " << request.requestId
             << " | Ambulance: " << request.ambulanceId
             << " | Severity: " << request.severity
             << " | Waiting Time: " << request.waitingTime
             << " minutes" << endl;
    }
}