#ifndef SCHEDULING_MANAGER_H
#define SCHEDULING_MANAGER_H

#include "RequestQueue.h"
#include "EmergencyRequest.h"

class SchedulingManager
{
private:
    RequestQueue queue;

public:
    void submitRequest(const EmergencyRequest& request);

    void displayPendingRequests() const;

    bool hasPendingRequests() const;

    int getPendingCount() const;

    EmergencyRequest processNextRequest();
};

#endif