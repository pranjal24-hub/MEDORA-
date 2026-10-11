#include <iostream>
#include <stdexcept>
#include "RequestStatus.h"

using namespace std;

void RequestStatusManager::registerRequest(int requestId)
{
    if (requestId <= 0)
    {
        throw invalid_argument("Invalid request ID.");
    }

    if (statusMap.find(requestId) != statusMap.end())
    {
        throw invalid_argument("Request is already registered.");
    }

    statusMap[requestId] = RequestState::Pending;

    cout << "Request " << requestId
         << " registered with Pending status." << endl;
}

bool RequestStatusManager::updateStatus(
    int requestId, RequestState newStatus)
{
    auto it = statusMap.find(requestId);

    if (it == statusMap.end())
    {
        cout << "Request not found." << endl;
        return false;
    }

    RequestState currentStatus = it->second;

    bool validTransition = false;

    if (currentStatus == RequestState::Pending)
    {
        validTransition =
            (newStatus == RequestState::Processing ||
             newStatus == RequestState::Cancelled);
    }
    else if (currentStatus == RequestState::Processing)
    {
        validTransition =
            (newStatus == RequestState::Completed ||
             newStatus == RequestState::Cancelled);
    }

    if (!validTransition)
    {
        cout << "Invalid status transition." << endl;
        return false;
    }

    it->second = newStatus;

    cout << "Request " << requestId
         << " status updated to "
         << getStatusName(newStatus) << "." << endl;

    return true;
}

RequestState RequestStatusManager::getStatus(
    int requestId) const
{
    auto it = statusMap.find(requestId);

    if (it == statusMap.end())
    {
        throw out_of_range("Request ID not found.");
    }

    return it->second;
}

string RequestStatusManager::getStatusName(RequestState status)
{
    switch (status)
    {
        case RequestState::Pending:
            return "Pending";

        case RequestState::Processing:
            return "Processing";

        case RequestState::Completed:
            return "Completed";

        case RequestState::Cancelled:
            return "Cancelled";
    }

    return "Unknown";
}

void RequestStatusManager::displayStatus(int requestId) const
{
    try
    {
        cout << "Request ID: " << requestId
             << " | Status: "
             << getStatusName(getStatus(requestId))
             << endl;
    }
    catch (const out_of_range& e)
    {
        cout << e.what() << endl;
    }
}