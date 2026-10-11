#ifndef REQUEST_QUEUE_H
#define REQUEST_QUEUE_H

#include <vector>
#include "EmergencyRequest.h"

using namespace std;

class RequestQueue
{
private:
    vector<EmergencyRequest> requests;

public:
    void addRequest(const EmergencyRequest& request);

    bool isEmpty() const;

    int size() const;

    EmergencyRequest getNextRequest();

    void displayQueue() const;
};

#endif